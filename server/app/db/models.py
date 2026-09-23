from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db.base import (
    Base,
    OptimisticLockMixin,
    TimestampMixin,
    ULIDPrimaryKeyMixin,
)


class PgVector(UserDefinedType):
    """pgvector列类型，仅用于元数据声明与比较。"""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "vector(384)"


class Job(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """统一异步任务：解析、索引、Embedding等共用同一状态合同。"""

    __tablename__ = "jobs"

    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    stage: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_jobs_status",
        ),
        UniqueConstraint("kind", "idempotency_key", name="uq_jobs_kind_idempotency"),
    )


class EvidenceTicket(Base, ULIDPrimaryKeyMixin):
    """短期证据票据：检索结果的可点击凭证，读取时重新校验权限。"""

    __tablename__ = "evidence_tickets"

    chunk_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(26), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    material_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeChunk(Base):
    """检索分块（含pgvector列与生成列），由迁移0005管理，跳过自动生成。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index(
            "ix_knowledge_chunks_tsv",
            "text_tsv",
            postgresql_using="gin",
        ),
        Index(
            "ix_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_knowledge_chunks_version_order",
            "material_version_id",
            "reading_order",
        ),
        Index("ix_knowledge_chunks_source_object", "source_object_id"),
        Index("ix_knowledge_chunks_retrieval_unit", "retrieval_unit_id"),
        {"info": {"skip_autogenerate": True}},
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    # 新索引可回溯到唯一教材对象与 V3 RetrievalUnit；旧索引迁移期允许为空。
    source_object_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id")
    )
    retrieval_unit_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("retrieval_units.id")
    )
    chapter_object_id: Mapped[str | None] = mapped_column(String(26))
    chapter_path: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    physical_page: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_version: Mapped[str | None] = mapped_column(String(50))
    embedding: Mapped[object | None] = mapped_column(PgVector())
    text_tsv: Mapped[object | None] = mapped_column(
        postgresql.TSVECTOR,
        Computed("to_tsvector('simple', text)", persisted=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatSession(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "chat_sessions"

    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    chapter_object_id: Mapped[str | None] = mapped_column(String(26))
    question_version_id: Mapped[str | None] = mapped_column(String(26))
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    parent_session_id: Mapped[str | None] = mapped_column(String(26), index=True)
    is_branch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    branch_source_turn_id: Mapped[str | None] = mapped_column(String(26))
    branch_selection: Mapped[str | None] = mapped_column(Text)
    merge_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "mode IN ('course_qa','tutor','question_coach','review')",
            name="ck_chat_sessions_mode",
        ),
        CheckConstraint("status IN ('active','closed')", name="ck_chat_sessions_status"),
    )


class ChatTurn(Base, ULIDPrimaryKeyMixin):
    __tablename__ = "chat_turns"

    session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    client_turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSON)
    verification: Mapped[dict | None] = mapped_column(JSON)
    refusal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    finish_reason: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("session_id", "client_turn_id", name="uq_chat_turns_client_id"),
        CheckConstraint("role IN ('student','tutor')", name="ck_chat_turns_role"),
    )


class LearningSession(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """服务端驱动的学习状态机：状态与提示层级只能由服务端转移。"""

    __tablename__ = "learning_sessions"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    material_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    chapter_object_id: Mapped[str | None] = mapped_column(String(26))
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="diagnose")
    hint_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tutor_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('diagnose','teach','check','hint','practice','summary','completed')",
            name="ck_learning_sessions_state",
        ),
        CheckConstraint(
            "status IN ('active','paused','closed')",
            name="ck_learning_sessions_status",
        ),
    )


class Question(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "questions"

    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    current_version_id: Mapped[str | None] = mapped_column(String(26))
    origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="teacher", server_default="teacher"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','approved','published','rejected','archived')",
            name="ck_questions_status",
        ),
        CheckConstraint("origin IN ('teacher','agent')", name="ck_questions_origin"),
    )


class QuestionVersion(Base, ULIDPrimaryKeyMixin):
    """不可变题目版本：作答与引用始终绑定具体版本。"""

    __tablename__ = "question_versions"

    question_id: Mapped[str] = mapped_column(String(26), ForeignKey("questions.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSON)
    answer: Mapped[dict | None] = mapped_column(JSON)
    rubric: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_point_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("question_id", "version_no", name="uq_question_versions_no"),
        CheckConstraint(
            "type IN ('single','multiple','true_false','short_answer','essay')",
            name="ck_question_versions_type",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_question_versions_difficulty"),
    )


class Assessment(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "assessments"

    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_policy: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="full_after_submit",
        server_default="full_after_submit",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "ai_policy IN ('disabled','direction_only','full_after_submit')",
            name="ck_assessments_ai_policy",
        ),
        CheckConstraint("status IN ('draft','published','closed')", name="ck_assessments_status"),
    )


class AssessmentItem(Base, ULIDPrimaryKeyMixin):
    __tablename__ = "assessment_items"

    assessment_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("assessments.id"), nullable=False
    )
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    points: Mapped[float] = mapped_column(nullable=False, default=1.0)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("assessment_id", "question_version_id", name="uq_assessment_items"),
    )


class Attempt(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "attempts"

    assessment_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("assessments.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress", server_default="in_progress"
    )
    score: Mapped[float | None] = mapped_column()
    grading_status: Mapped[str | None] = mapped_column(String(20))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coach_hints: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress','submitted','graded')", name="ck_attempts_status"
        ),
    )


class AttemptAnswer(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "attempt_answers"

    attempt_id: Mapped[str] = mapped_column(String(26), ForeignKey("attempts.id"), nullable=False)
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    response: Mapped[dict | None] = mapped_column(JSON)
    client_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_earned: Mapped[float | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_version_id", name="uq_attempt_answers"),
    )


class ReviewTask(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """错题归因产生的复习任务：间隔到期，完成后关闭。"""

    __tablename__ = "review_tasks"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    question_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_attempt_id: Mapped[str | None] = mapped_column(String(26))
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "reason IN ('wrong_answer','review_schedule')", name="ck_review_tasks_reason"
        ),
        CheckConstraint("status IN ('pending','done','dismissed')", name="ck_review_tasks_status"),
    )


class LearningEvidence(Base, ULIDPrimaryKeyMixin):
    """掌握度证据账本：只追加不可变，每次状态变化可追溯到证据。"""

    __tablename__ = "learning_evidences"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=False)
    question_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(26))
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weight: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_learning_evidences_user_course",
            "user_id",
            "course_id",
        ),
        CheckConstraint(
            "source_type IN ('formal_quiz','practice','review')",
            name="ck_learning_evidences_source",
        ),
    )


class MasteryState(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """聚合后的当前掌握状态。未学习/学习中/需巩固/基本掌握/已掌握。"""

    __tablename__ = "mastery_states"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_ratio: Mapped[float] = mapped_column(nullable=False, default=0.0)
    weight_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    last_evidence_id: Mapped[str | None] = mapped_column(String(26))

    __table_args__ = (
        Index(
            "ix_mastery_states_user_course",
            "user_id",
            "course_id",
        ),
        UniqueConstraint(
            "user_id", "course_id", "knowledge_point", name="uq_mastery_user_course_kp"
        ),
        CheckConstraint(
            "state IN ('not_started','learning','needs_consolidation','proficient','mastered')",
            name="ck_mastery_state",
        ),
    )


class MemoryItem(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """分层学习记忆：L1候选/L2稳定/L3偏好；过时隐藏不删除；替代关系可审计。"""

    __tablename__ = "memory_items"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str | None] = mapped_column(String(26))
    layer: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    superseded_by_id: Mapped[str | None] = mapped_column(String(26))
    stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_memory_items_user", "user_id"),
        CheckConstraint("layer IN ('L1','L2','L3')", name="ck_memory_items_layer"),
        CheckConstraint(
            "source_type IN ('quiz','tutor','practice','user','review')",
            name="ck_memory_items_source",
        ),
    )


class ModelCallLog(Base, ULIDPrimaryKeyMixin):
    """模型网关调用日志：不含密钥与原文，只记元数据。"""

    __tablename__ = "model_call_logs"

    purpose: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[str | None] = mapped_column(String(26))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','timeout','error','budget_exceeded','circuit_open')",
            name="ck_model_call_logs_status",
        ),
    )


class Organization(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )


class User(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "users"

    organization_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("organizations.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_teacher: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class AuthSession(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (Index("ix_auth_sessions_user_active", "user_id", "expires_at"),)


class Course(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "courses"

    organization_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("organizations.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)


class CourseMember(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "course_members"

    course_id: Mapped[str] = mapped_column(String(26), ForeignKey("courses.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )

    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_course_members_course_user"),
        CheckConstraint("role IN ('teacher','student','assistant')", name="ck_course_members_role"),
        CheckConstraint("status IN ('active','removed')", name="ck_course_members_status"),
    )


class AuditLog(Base, ULIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    actor_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(26))
    course_id: Mapped[str | None] = mapped_column(String(26))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IdempotencyRecord(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "user_id",
            "endpoint",
            name="uq_idempotency_key_user_endpoint",
        ),
    )


class Material(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "materials"

    course_id: Mapped[str] = mapped_column(String(26), ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    material_type: Mapped[str] = mapped_column(String(30), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(26))

    __table_args__ = (
        CheckConstraint(
            "material_type IN ('textbook','slides','handout','exercise','reference','other')",
            name="ck_materials_type",
        ),
        CheckConstraint("visibility IN ('draft','published')", name="ck_materials_visibility"),
        CheckConstraint("status IN ('active','archived','deleted')", name="ck_materials_status"),
        Index("ix_materials_course", "course_id", "status"),
    )


class MaterialVersion(Base, ULIDPrimaryKeyMixin):
    """教材版本：一旦上传成功即不可变，更新必须创建新版本。"""

    __tablename__ = "material_versions"

    material_id: Mapped[str] = mapped_column(String(26), ForeignKey("materials.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="uploading", server_default="uploading"
    )
    object_key: Mapped[str | None] = mapped_column(String(512))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(100))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    quality_report: Mapped[dict | None] = mapped_column(JSON)
    canonical_pdf_key: Mapped[str | None] = mapped_column(String(512))
    render_manifest: Mapped[dict | None] = mapped_column(JSON)
    render_version: Mapped[str | None] = mapped_column(String(50))
    pipeline_version: Mapped[str | None] = mapped_column(String(50))
    quality_gate_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )

    __table_args__ = (
        UniqueConstraint("material_id", "version_no", name="uq_material_versions_no"),
        CheckConstraint(
            "status IN ('uploading','uploaded','failed','parsing','parsed','removed')",
            name="ck_material_versions_status",
        ),
        CheckConstraint(
            "quality_gate_status IN ('pending','blocked','approved')",
            name="ck_material_versions_quality_gate",
        ),
    )


class KnowledgeObject(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教材解析中间格式对象。raw_content不可修改，教师修正写入override层。"""

    __tablename__ = "knowledge_objects"

    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    chapter_path: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    parent_id: Mapped[str | None] = mapped_column(String(26))
    physical_page: Mapped[int] = mapped_column(Integer, nullable=False)
    printed_page: Mapped[int | None] = mapped_column(Integer)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list | None] = mapped_column(JSON)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_content: Mapped[str | None] = mapped_column(Text)
    parser: Mapped[str] = mapped_column(String(50), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.9)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    override: Mapped[list | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "type IN ('chapter','paragraph','figure','table','formula')",
            name="ck_knowledge_objects_type",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected','corrected')",
            name="ck_knowledge_objects_review",
        ),
        Index(
            "ix_knowledge_objects_version_order",
            "material_version_id",
            "reading_order",
        ),
    )


class ObjectAsset(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """教材版本的不可变二进制产物：页面、裁剪、快照和解析调试资产。"""

    __tablename__ = "object_assets"

    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    knowledge_object_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id")
    )
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    physical_page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list | None] = mapped_column(JSON)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    render_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ready", server_default="ready"
    )

    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('canonical_pdf','page_image','object_crop','parser_payload')",
            name="ck_object_assets_type",
        ),
        CheckConstraint("status IN ('ready','failed','removed')", name="ck_object_assets_status"),
        UniqueConstraint("material_version_id", "object_key", name="uq_object_assets_version_key"),
        Index("ix_object_assets_version_page", "material_version_id", "physical_page"),
    )


class ObjectRepresentation(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """可重建的对象派生表示，不能单独成为教材事实引用。"""

    __tablename__ = "object_representations"

    knowledge_object_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id"), nullable=False
    )
    representation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[dict | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ready", server_default="ready"
    )

    __table_args__ = (
        CheckConstraint(
            "representation_type IN "
            "('ocr','caption','table_json','table_markdown','latex','semantic_description','retrieval_text')",
            name="ck_object_representations_type",
        ),
        CheckConstraint(
            "status IN ('queued','ready','failed','superseded')",
            name="ck_object_representations_status",
        ),
        UniqueConstraint(
            "knowledge_object_id",
            "representation_type",
            "generator_version",
            "source_hash",
            name="uq_object_representations_source",
        ),
        Index("ix_object_representations_object", "knowledge_object_id", "representation_type"),
    )


class ObjectRelation(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """经解析或审核确认的教材对象关系，用于最小证据闭包。"""

    __tablename__ = "object_relations"

    source_object_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id"), nullable=False
    )
    target_object_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.9)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )

    __table_args__ = (
        CheckConstraint(
            "relation_type IN "
            "('parent_of','previous','next','caption_of','references','continues_on','explains',"
            "'same_table','same_figure')",
            name="ck_object_relations_type",
        ),
        CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name="ck_object_relations_review",
        ),
        UniqueConstraint(
            "source_object_id", "target_object_id", "relation_type", name="uq_object_relations_edge"
        ),
        Index("ix_object_relations_source", "source_object_id", "relation_type"),
        Index("ix_object_relations_target", "target_object_id", "relation_type"),
    )


class RetrievalUnit(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """只用于召回和排序的派生单元，显式区别于生成上下文。"""

    __tablename__ = "retrieval_units"

    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    source_object_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id"), nullable=False
    )
    parent_object_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id")
    )
    representation_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("object_representations.id")
    )
    unit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    channel_hint: Mapped[str] = mapped_column(String(20), nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list | None] = mapped_column(JSON)
    text_content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    build_strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    build_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ready", server_default="ready"
    )

    __table_args__ = (
        CheckConstraint(
            "unit_type IN ('text_child','table','table_row','table_column','table_cells',"
            "'image','page','equation')",
            name="ck_retrieval_units_type",
        ),
        CheckConstraint(
            "channel_hint IN ('sparse','dense','visual','multi_vector')",
            name="ck_retrieval_units_channel",
        ),
        CheckConstraint(
            "status IN ('queued','ready','failed','superseded')", name="ck_retrieval_units_status"
        ),
        UniqueConstraint(
            "source_object_id",
            "representation_id",
            "unit_type",
            "build_strategy",
            "build_version",
            "content_hash",
            name="uq_retrieval_units_build",
        ),
        Index("ix_retrieval_units_version_type", "material_version_id", "unit_type"),
        Index("ix_retrieval_units_source", "source_object_id"),
    )


class RetrievalIndexEntry(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """检索索引元数据；向量载荷由对应 Provider/索引适配器管理。"""

    __tablename__ = "retrieval_index_entries"

    retrieval_unit_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("retrieval_units.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension: Mapped[int | None] = mapped_column(Integer)
    index_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "channel IN ('sparse','dense','visual','multi_vector')",
            name="ck_retrieval_index_entries_channel",
        ),
        CheckConstraint(
            "status IN ('queued','building','ready','failed','superseded')",
            name="ck_retrieval_index_entries_status",
        ),
        UniqueConstraint(
            "retrieval_unit_id",
            "channel",
            "provider",
            "model",
            "model_version",
            "index_version",
            "source_hash",
            name="uq_retrieval_index_entries_version",
        ),
        Index("ix_retrieval_index_entries_lookup", "channel", "index_version", "status"),
    )


class ParseReviewIssue(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """教师发布前必须处理的解析与质量问题。"""

    __tablename__ = "parse_review_issues"

    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    knowledge_object_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("knowledge_objects.id")
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "severity IN ('blocking','warning','info')", name="ck_parse_review_issues_severity"
        ),
        CheckConstraint(
            "status IN ('open','resolved','ignored')", name="ck_parse_review_issues_status"
        ),
        UniqueConstraint(
            "material_version_id",
            "knowledge_object_id",
            "code",
            "status",
            name="uq_parse_review_issues_open",
        ),
        Index("ix_parse_review_issues_version", "material_version_id", "severity", "status"),
    )
