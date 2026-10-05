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
from sqlalchemy import (
    text as sql_text,
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
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    worker_backend: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_process", server_default="in_process"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        Index("ix_jobs_heartbeat", "status", "last_heartbeat_at"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_jobs_status",
        ),
        CheckConstraint("worker_backend IN ('in_process','celery')", name="ck_jobs_worker_backend"),
        UniqueConstraint("kind", "idempotency_key", name="uq_jobs_kind_idempotency"),
    )


class EvidencePointer(Base, ULIDPrimaryKeyMixin):
    """不可变教材引用快照；访问时仍须重新校验当前课程权限。"""

    __tablename__ = "evidence_pointers"

    course_id: Mapped[str] = mapped_column(String(26), ForeignKey("courses.id"), nullable=False)
    material_id: Mapped[str] = mapped_column(String(26), ForeignKey("materials.id"), nullable=False)
    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    # 这是来源身份快照，不设 FK：重解析删除旧 KnowledgeObject 时不得破坏历史引用。
    source_object_id: Mapped[str | None] = mapped_column(String(26))
    retrieval_unit_id: Mapped[str | None] = mapped_column(String(26))
    material_title: Mapped[str] = mapped_column(String(200), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chapter_path: Mapped[str | None] = mapped_column(String(1000))
    physical_page: Mapped[int | None] = mapped_column(Integer)
    reading_order: Mapped[int | None] = mapped_column(Integer)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    coordinate_space: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pdf_user_bottom_left"
    )
    bbox: Mapped[list | None] = mapped_column(JSON)
    # 来源对象在生成时对应的一个或多个固定版面锚点；旧记录仍用主页投影兼容读取。
    anchors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "physical_page IS NULL OR physical_page >= 1", name="ck_evidence_pointer_page"
        ),
        CheckConstraint(
            "coordinate_space IN ('pdf_user_bottom_left','unavailable')",
            name="ck_evidence_pointer_coordinate_space",
        ),
        Index("ix_evidence_pointers_course_created", "course_id", "created_at"),
        Index("ix_evidence_pointers_version_object", "material_version_id", "source_object_id"),
    )


class EvidenceTicket(Base, ULIDPrimaryKeyMixin):
    """短期证据票据：检索结果的可点击凭证，读取时重新校验权限。"""

    __tablename__ = "evidence_tickets"

    chunk_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(26), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    material_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    pointer_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("evidence_pointers.id"), index=True
    )
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
    physical_page: Mapped[int | None] = mapped_column(Integer)
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
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    course_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT")
    )
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
    branch_merge_key: Mapped[str | None] = mapped_column(String(128))
    branch_merge_payload_hash: Mapped[str | None] = mapped_column(String(64))
    branch_merge_result_turn_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey(
            "chat_turns.id",
            name="fk_chat_sessions_branch_merge_result_turn",
            use_alter=True,
        ),
    )
    branch_merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "mode IN ('course_qa','tutor','question_coach','review')",
            name="ck_chat_sessions_mode",
        ),
        CheckConstraint("status IN ('active','closed')", name="ck_chat_sessions_status"),
        CheckConstraint(
            "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
            name="ck_chat_sessions_release_pair",
        ),
        Index("ix_chat_sessions_release_assignment", "course_release_assignment_id"),
        CheckConstraint(
            "(branch_merge_key IS NULL AND branch_merge_payload_hash IS NULL "
            "AND branch_merge_result_turn_id IS NULL AND branch_merged_at IS NULL) OR "
            "(is_branch = true AND branch_merge_key IS NOT NULL "
            "AND branch_merge_payload_hash IS NOT NULL "
            "AND branch_merge_result_turn_id IS NOT NULL AND branch_merged_at IS NOT NULL)",
            name="ck_chat_sessions_branch_merge_receipt",
        ),
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
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    course_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT")
    )
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
        Index("ix_learning_sessions_release_assignment", "course_release_assignment_id"),
        CheckConstraint(
            "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
            name="ck_learning_sessions_release_pair",
        ),
    )


class CurrentLearningTask(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """学习任务聚合；与旧 LearningSession 适配共存，保存目标与版本快照。"""

    __tablename__ = "current_learning_tasks"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    legacy_session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False
    )
    material_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    chapter_object_id: Mapped[str | None] = mapped_column(String(26))
    goal: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    release_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completion: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("legacy_session_id", name="uq_current_learning_tasks_legacy_session"),
        CheckConstraint(
            "status IN ('active','paused','completed','closed')",
            name="ck_current_learning_tasks_status",
        ),
        Index("ix_current_learning_tasks_user_course", "user_id", "course_id", "updated_at"),
    )


class TeachingSession(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教学运行时聚合：状态机上下文与单回合版本。"""

    __tablename__ = "teaching_sessions"

    task_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("current_learning_tasks.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="diagnose")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    hint_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    __table_args__ = (
        UniqueConstraint("task_id", name="uq_teaching_sessions_task"),
        CheckConstraint(
            "status IN ('active','paused','closed')", name="ck_teaching_sessions_status"
        ),
    )


class LearningEpisode(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """有限任务的可追溯 Episode；暂停/恢复复用同一 Episode。"""

    __tablename__ = "learning_episodes"

    task_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("current_learning_tasks.id", ondelete="CASCADE"), nullable=False
    )
    teaching_session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("teaching_sessions.id", ondelete="CASCADE"), nullable=False
    )
    episode_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("task_id", "episode_no", name="uq_learning_episodes_task_no"),
        CheckConstraint(
            "status IN ('active','paused','completed','closed')", name="ck_learning_episodes_status"
        ),
    )


class CaseSession(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """学生案例推理会话；案例快照不可被客户端改写。"""

    __tablename__ = "case_sessions"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    case_key: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    case_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','completed','abandoned')", name="ck_case_sessions_status"
        ),
        Index("ix_case_sessions_user_course", "user_id", "course_id", "updated_at"),
    )


class MiniLabSession(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """浏览器实验运行时的服务端会话与结果快照。"""

    __tablename__ = "mini_lab_sessions"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    lab_key: Mapped[str] = mapped_column(String(80), nullable=False)
    definition_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="intro")
    trial_data: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    derived_measure: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_key: Mapped[str | None] = mapped_column(String(128))
    invalidation_payload_hash: Mapped[str | None] = mapped_column(String(64))
    invalidated_by_user_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','invalidated')",
            name="ck_mini_lab_sessions_status",
        ),
        CheckConstraint(
            "phase IN ('intro','predict','run','inspect','explain','summary')",
            name="ck_mini_lab_sessions_phase",
        ),
        Index("ix_mini_lab_sessions_user_course", "user_id", "course_id", "updated_at"),
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
    purpose: Mapped[str | None] = mapped_column(String(20))
    result_visibility_policy: Mapped[str | None] = mapped_column(String(40))
    results_released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "ai_policy IN ('disabled','direction_only','full_after_submit')",
            name="ck_assessments_ai_policy",
        ),
        CheckConstraint("status IN ('draft','published','closed')", name="ck_assessments_status"),
        CheckConstraint(
            "purpose IS NULL OR purpose IN ('practice','formal')",
            name="ck_assessments_purpose",
        ),
        CheckConstraint(
            "result_visibility_policy IS NULL OR result_visibility_policy IN "
            "('immediate_after_submission','after_close','after_grading','manual_release')",
            name="ck_assessments_result_visibility",
        ),
        CheckConstraint(
            "purpose IS DISTINCT FROM 'formal' OR result_visibility_policy IS DISTINCT FROM "
            "'immediate_after_submission'",
            name="ck_assessments_formal_visibility",
        ),
        Index("ix_assessments_release_assignment", "course_release_assignment_id"),
    )


class AssessmentItem(Base, ULIDPrimaryKeyMixin):
    __tablename__ = "assessment_items"

    assessment_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("assessments.id"), nullable=False
    )
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    rubric_version_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("rubric_versions.id", ondelete="RESTRICT")
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
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    course_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT")
    )
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
        Index("ix_attempts_release_assignment", "course_release_assignment_id"),
        CheckConstraint(
            "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
            name="ck_attempts_release_pair",
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
    flagged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    points_earned: Mapped[float | None] = mapped_column()

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_version_id", name="uq_attempt_answers"),
    )


class TeacherGradingDecision(Base, ULIDPrimaryKeyMixin):
    """不可变的教师主观题评分决定；更正通过新版本追加。"""

    __tablename__ = "teacher_grading_decisions"

    attempt_id: Mapped[str] = mapped_column(String(26), ForeignKey("attempts.id"), nullable=False)
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    grader_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    points_awarded: Mapped[float] = mapped_column(nullable=False)
    max_points: Mapped[float] = mapped_column(nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("teacher_grading_decisions.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "question_version_id",
            "decision_version",
            name="uq_teacher_grading_decisions_version",
        ),
        CheckConstraint(
            "decision_version >= 1 AND points_awarded >= 0 AND points_awarded <= max_points",
            name="ck_teacher_grading_decisions_score_range",
        ),
        Index("ix_teacher_grading_decisions_attempt", "attempt_id", "question_version_id"),
    )


class ScoreRecord(Base, ULIDPrimaryKeyMixin):
    """不可变的正式成绩快照；每次教师 override 生成新版本。"""

    __tablename__ = "score_records"

    attempt_id: Mapped[str] = mapped_column(String(26), ForeignKey("attempts.id"), nullable=False)
    score_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    max_score: Mapped[float] = mapped_column(nullable=False)
    breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("score_records.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("attempt_id", "score_version", name="uq_score_records_attempt_version"),
        CheckConstraint(
            "score_version >= 1 AND score >= 0 AND score <= max_score",
            name="ck_score_records_score_range",
        ),
        Index("ix_score_records_attempt_version", "attempt_id", "score_version"),
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
    qualification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    qualification_reason: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "reason IN ('wrong_answer','review_schedule')", name="ck_review_tasks_reason"
        ),
        CheckConstraint("status IN ('pending','done','dismissed')", name="ck_review_tasks_status"),
        CheckConstraint(
            "qualification_status IN ('pending','qualified','rejected')",
            name="ck_review_tasks_qualification",
        ),
    )


class WrongAnswerTrace(Base, ULIDPrimaryKeyMixin):
    """正式测评的判错索引；只存来源与作答存在性，不存答案正文。"""

    __tablename__ = "wrong_answer_traces"

    attempt_id: Mapped[str] = mapped_column(String(26), ForeignKey("attempts.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    answer_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "question_version_id", name="uq_wrong_answer_trace_attempt_question"
        ),
        Index("ix_wrong_answer_traces_user_course", "user_id", "course_id", "created_at"),
    )


class QuestionQualityFeedback(Base, ULIDPrimaryKeyMixin):
    """学生对其已完成测评题目的质量反馈；原文保留，教师处置另有审计。"""

    __tablename__ = "question_quality_feedback"

    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    attempt_id: Mapped[str] = mapped_column(String(26), ForeignKey("attempts.id"), nullable=False)
    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    resolution_action: Mapped[str | None] = mapped_column(String(20))
    resolution_rationale: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "attempt_id",
            "question_version_id",
            name="uq_question_quality_feedback_attempt_question",
        ),
        CheckConstraint(
            "category IN ('answer_key','ambiguous','outdated','other')",
            name="ck_question_quality_feedback_category",
        ),
        CheckConstraint(
            "status IN ('pending','accepted','rejected','invalidated')",
            name="ck_question_quality_feedback_status",
        ),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('accept','reject','invalidate')",
            name="ck_question_quality_feedback_action",
        ),
        Index(
            "ix_question_quality_feedback_course_status",
            "course_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_question_quality_feedback_question",
            "question_version_id",
            "status",
        ),
    )


class LearningEvidence(Base, ULIDPrimaryKeyMixin):
    """掌握度证据账本：只追加不可变，每次状态变化可追溯到证据。"""

    __tablename__ = "learning_evidences"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    course_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT")
    )
    knowledge_point: Mapped[str] = mapped_column(String(200), nullable=False)
    question_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(26))
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    dimension: Mapped[str] = mapped_column(
        String(20), nullable=False, default="understand", server_default="understand"
    )
    independence_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    context_key: Mapped[str | None] = mapped_column(String(100))
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="valid", server_default="valid"
    )
    invalidated_reason: Mapped[str | None] = mapped_column(String(500))
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
        Index("ix_learning_evidences_release_assignment", "course_release_assignment_id"),
        CheckConstraint(
            "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
            name="ck_learning_evidences_release_pair",
        ),
        CheckConstraint(
            "source_type IN ('formal_quiz','practice','review')",
            name="ck_learning_evidences_source",
        ),
        CheckConstraint(
            "dimension IN ('recall','understand','discriminate','apply','transfer','retention')",
            name="ck_learning_evidences_dimension",
        ),
        CheckConstraint(
            "independence_status IN ('independent','supported','unknown')",
            name="ck_learning_evidences_independence",
        ),
        CheckConstraint(
            "quality_status IN ('valid','invalidated')",
            name="ck_learning_evidences_quality",
        ),
    )


class LearningEvent(Base, ULIDPrimaryKeyMixin):
    """原始学习事件；客户端只能追加待资格化事件，不能直接写掌握或成绩。"""

    __tablename__ = "learning_events"

    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    qualification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    qualification_reason: Mapped[str | None] = mapped_column(String(500))
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_learning_events_user_key"),
        CheckConstraint(
            "event_type IN ('task_viewed','answer_submitted','tutor_responded',"
            "'lab_trial_completed','feedback_submitted')",
            name="ck_learning_events_type",
        ),
        CheckConstraint(
            "source_type IN ('tutor','assessment','practice','review','lab','system')",
            name="ck_learning_events_source",
        ),
        CheckConstraint(
            "qualification_status IN ('pending','qualified','rejected','invalidated')",
            name="ck_learning_events_qualification",
        ),
        Index("ix_learning_events_user_course_time", "user_id", "course_id", "occurred_at"),
    )


class LearningQualification(Base, ULIDPrimaryKeyMixin):
    """原始事件的确定性资格化结果；同一事件只能生成一个资格化决策。"""

    __tablename__ = "learning_qualifications"

    event_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("learning_events.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(26), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_learning_qualifications_event"),
        CheckConstraint(
            "status IN ('qualified','rejected','invalidated')",
            name="ck_learning_qualifications_status",
        ),
        Index(
            "ix_learning_qualifications_user_course",
            "user_id",
            "course_id",
            "evaluated_at",
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
    context_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    independent_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_evidence_id: Mapped[str | None] = mapped_column(String(26))
    algorithm_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mastery-v2-independent-context"
    )
    state_reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")

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
    provenance_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default="inferred", server_default="inferred"
    )
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conflict_group_id: Mapped[str | None] = mapped_column(String(26))
    conflict_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )
    conflict_resolution_reason: Mapped[str | None] = mapped_column(Text)
    conflict_resolved_by_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    conflict_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    superseded_by_id: Mapped[str | None] = mapped_column(String(26))
    stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_memory_items_user", "user_id"),
        Index("ix_memory_items_expiry", "user_id", "expires_at"),
        Index("ix_memory_items_conflict_group", "user_id", "conflict_group_id"),
        CheckConstraint("layer IN ('L1','L2','L3')", name="ck_memory_items_layer"),
        CheckConstraint(
            "provenance_level IN ('observed','inferred','explicit','teacher_confirmed')",
            name="ck_memory_items_provenance_level",
        ),
        CheckConstraint(
            "conflict_status IN ('none','open','resolved')",
            name="ck_memory_items_conflict_status",
        ),
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


class CourseClass(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """课程下的教学班级；班级是权限与学情聚合的独立 Scope。"""

    __tablename__ = "course_classes"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("course_id", "code", name="uq_course_classes_course_code"),
        CheckConstraint("status IN ('active','archived')", name="ck_course_classes_status"),
        Index("ix_course_classes_course_status", "course_id", "status"),
    )


class ClassMember(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """班级学生归属；与课程成员分离，支持班级级学情聚合。"""

    __tablename__ = "class_members"

    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),
        CheckConstraint("status IN ('active','removed')", name="ck_class_members_status"),
        Index("ix_class_members_class_status", "class_id", "status"),
    )


class TeacherAssignment(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教师与班级的显式任课关系，不从平台管理员身份推断。"""

    __tablename__ = "teacher_assignments"

    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    assignment_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    assigned_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("class_id", "teacher_id", name="uq_teacher_assignments_class_teacher"),
        CheckConstraint(
            "assignment_role IN ('lead','assistant')", name="ck_teacher_assignments_role"
        ),
        CheckConstraint("status IN ('active','ended')", name="ck_teacher_assignments_status"),
        Index("ix_teacher_assignments_teacher_status", "teacher_id", "status"),
    )


class RoleAssignment(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """显式角色与资源 Scope；平台管理员标记本身不等于课程教学权限。"""

    __tablename__ = "role_assignments"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    granted_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint(
            "user_id", "role", "scope_type", "scope_id", name="uq_role_assignments_scope"
        ),
        CheckConstraint(
            "role IN ('student','teacher','assistant','course_designer',"
            "'course_publisher','admin')",
            name="ck_role_assignments_role",
        ),
        CheckConstraint(
            "scope_type IN ('platform','course','class')",
            name="ck_role_assignments_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'platform' AND scope_id IS NULL) OR "
            "(scope_type IN ('course','class') AND scope_id IS NOT NULL)",
            name="ck_role_assignments_scope_id",
        ),
        CheckConstraint("status IN ('active','revoked')", name="ck_role_assignments_status"),
        Index("ix_role_assignments_user_status", "user_id", "status"),
        Index("ix_role_assignments_scope_status", "scope_type", "scope_id", "status"),
        Index(
            "uq_role_assignments_active_scope",
            "user_id",
            "role",
            "scope_type",
            sql_text("COALESCE(scope_id, '')"),
            unique=True,
            postgresql_where=sql_text("status = 'active'"),
        ),
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


class UserPreference(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """用户显式偏好；只影响表示和通知，不得越过服务端安全策略。"""

    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_preferences_user"),
        Index("ix_user_preferences_user", "user_id"),
    )


class PrivacyDeletionRequest(Base, ULIDPrimaryKeyMixin):
    """持久隐私删除任务与处理回执；不保存请求正文或明文查询凭证。"""

    __tablename__ = "privacy_deletion_requests"

    subject_user_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    processed_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    retained_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    status_credential_hash: Mapped[str | None] = mapped_column(String(64))
    status_credential_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'failed', 'completed_with_retention')",
            name="ck_privacy_deletion_status",
        ),
        Index(
            "uq_privacy_deletion_status_credential_hash",
            "status_credential_hash",
            unique=True,
        ),
        Index("ix_privacy_deletion_requests_status_requested", "status", "requested_at"),
    )


class Notification(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """站内通知；只保存面向用户的摘要，不保存 Prompt 或敏感正文。"""

    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )


class OutboxEvent(Base, ULIDPrimaryKeyMixin):
    """事务内写入、可重试投递的跨模块事件。"""

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    producer: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_outbox_events_pending", "published_at", "occurred_at", "id"),
        Index("ix_outbox_events_type_occurred", "event_type", "occurred_at"),
        CheckConstraint("event_version > 0", name="ck_outbox_event_version_positive"),
        CheckConstraint("attempt_count >= 0", name="ck_outbox_attempt_count_nonnegative"),
    )


class OutboxConsumerReceipt(Base, ULIDPrimaryKeyMixin):
    """消费者幂等账本：同一事件对同一消费者只成功记账一次。"""

    __tablename__ = "outbox_consumer_receipts"

    event_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False
    )
    consumer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("event_id", "consumer_name", name="uq_outbox_consumer_event"),
        Index("ix_outbox_receipts_consumer", "consumer_name", "consumed_at"),
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


class UploadSession(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """可恢复浏览器直传会话；完成验收后才创建教材版本。"""

    __tablename__ = "upload_sessions"

    course_id: Mapped[str] = mapped_column(String(26), ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    material_type: Mapped[str] = mapped_column(String(30), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    part_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    multipart_upload_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created", server_default="created"
    )
    sha256: Mapped[str | None] = mapped_column(String(64))
    material_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("materials.id"))
    material_version_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("material_versions.id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('created','uploading','uploaded','verifying','completed',"
            "'failed','cancelled','expired')",
            name="ck_upload_sessions_status",
        ),
        CheckConstraint(
            "material_type IN ('textbook','slides','handout','exercise','reference','other')",
            name="ck_upload_sessions_material_type",
        ),
        Index("ix_upload_sessions_course_status", "course_id", "status", "created_at"),
        Index("ix_upload_sessions_creator_status", "created_by", "status"),
    )


class UploadPart(Base, TimestampMixin):
    """已确认的 MinIO Multipart 分片。"""

    __tablename__ = "upload_parts"

    upload_session_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("upload_sessions.id"), primary_key=True
    )
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    etag: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("part_number >= 1", name="ck_upload_parts_number"),
        CheckConstraint("size_bytes > 0", name="ck_upload_parts_size"),
    )


class DomainRelease(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """课程 Domain Pack 的不可变发布快照；Canonical 只存在于 published 版本。"""

    __tablename__ = "domain_releases"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pack_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[str | None] = mapped_column(Text)
    published_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("domain_releases.id"))

    __table_args__ = (
        UniqueConstraint("course_id", "version_no", name="uq_domain_releases_course_version"),
        CheckConstraint("version_no >= 1", name="ck_domain_releases_version"),
        CheckConstraint(
            "status IN ('draft','ready','published','deprecated')",
            name="ck_domain_releases_status",
        ),
        CheckConstraint("length(pack_sha256) = 64", name="ck_domain_releases_sha256"),
        Index("ix_domain_releases_course_status", "course_id", "status", "version_no"),
    )


class DomainReviewDecision(Base, ULIDPrimaryKeyMixin):
    """针对一个 Domain 对象版本的追加式审核决定；不覆盖候选原文。"""

    __tablename__ = "domain_review_decisions"

    domain_release_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("domain_releases.id", ondelete="CASCADE"), nullable=False
    )
    object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    object_key: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "object_type IN ('knowledge_point','relation','experiment','misconception')",
            name="ck_domain_review_object_type",
        ),
        CheckConstraint(
            "decision IN ('approved','rejected','changes_requested')",
            name="ck_domain_review_decision",
        ),
        Index(
            "ix_domain_review_decisions_release_object",
            "domain_release_id",
            "object_type",
            "object_key",
            "created_at",
        ),
    )


class PublicationSnapshot(Base, ULIDPrimaryKeyMixin):
    """一次原子发布所使用的教材、解析与索引版本快照。"""

    __tablename__ = "publication_snapshots"

    material_id: Mapped[str] = mapped_column(String(26), ForeignKey("materials.id"), nullable=False)
    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    parse_job_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("jobs.id"))
    index_job_id: Mapped[str] = mapped_column(String(26), ForeignKey("jobs.id"), nullable=False)
    domain_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("domain_releases.id", ondelete="RESTRICT")
    )
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    published_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "uq_publication_snapshots_current",
            "material_id",
            unique=True,
            postgresql_where=sql_text("superseded_at IS NULL"),
        ),
        Index(
            "ix_publication_snapshots_version",
            "material_version_id",
            "published_at",
        ),
    )


class CourseRelease(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """课程可运行版本；发布后 manifest 不原地修改。"""

    __tablename__ = "course_releases"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    domain_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("domain_releases.id", ondelete="RESTRICT")
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("course_id", "version_no", name="uq_course_releases_course_version"),
        CheckConstraint(
            "status IN ('draft','published','deprecated')", name="ck_course_releases_status"
        ),
        Index("ix_course_releases_course_status", "course_id", "status", "version_no"),
    )


class TeachingAssetVersion(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """受版本与课程 Release 约束的教学资产；内容只能通过新版本替换。"""

    __tablename__ = "teaching_asset_versions"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="SET NULL")
    )
    asset_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fallback_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "course_id", "asset_key", "version_no", name="uq_teaching_asset_course_key_version"
        ),
        CheckConstraint(
            "template IN ('explanation','comparison','variable_map','table','focus')",
            name="ck_teaching_asset_template",
        ),
        CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_teaching_asset_status"
        ),
        Index(
            "ix_teaching_asset_course_status",
            "course_id",
            "status",
            "asset_key",
            "version_no",
        ),
    )


class Intervention(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教师干预活动：目标快照冻结，完成与效果评估分离。"""

    __tablename__ = "interventions"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("course_classes.id", name="fk_teacher_observation_class", ondelete="SET NULL"),
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('reteach','practice_set','mini_lab','discussion','review')",
            name="ck_interventions_activity_type",
        ),
        CheckConstraint(
            "status IN ('draft','scheduled','active','completed','evaluated','archived')",
            name="ck_interventions_status",
        ),
        Index("ix_interventions_course_status", "course_id", "status", "created_at"),
        Index("ix_interventions_class_status", "class_id", "status", "created_at"),
    )


class InterventionRun(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """面向单个学生的干预执行实例；完成不等于掌握或证据合格。"""

    __tablename__ = "intervention_runs"

    intervention_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("interventions.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled", server_default="scheduled"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "intervention_id", "user_id", name="uq_intervention_runs_intervention_user"
        ),
        CheckConstraint(
            "status IN ('scheduled','in_progress','paused','completed','cancelled')",
            name="ck_intervention_runs_status",
        ),
        Index("ix_intervention_runs_intervention_status", "intervention_id", "status"),
        Index("ix_intervention_runs_user_status", "user_id", "status", "updated_at"),
    )


class TeacherObservation(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教师对学生学习表现的独立观察；审核结果不覆盖原始作答或掌握状态。"""

    __tablename__ = "teacher_observations"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="SET NULL")
    )
    student_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    qualification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    review_decision: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    algorithm_version: Mapped[str | None] = mapped_column(String(50))
    reviewed_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    review_reason: Mapped[str | None] = mapped_column(String(500))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    verification_event_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("learning_events.id", name="fk_teacher_observation_event", ondelete="SET NULL"),
    )
    verification_qualification_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey(
            "learning_qualifications.id",
            name="fk_teacher_observation_qualification",
            ondelete="SET NULL",
        ),
    )
    verification_evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    verification_algorithm_version: Mapped[str | None] = mapped_column(String(50))
    verification_reason: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "observation_type IN ('misconception','strategy','support_need','progress')",
            name="ck_teacher_observations_type",
        ),
        CheckConstraint(
            "qualification_status IN ('pending','qualified','rejected')",
            name="ck_teacher_observations_qualification",
        ),
        CheckConstraint(
            "review_decision IN ('pending','accepted','rejected')",
            name="ck_teacher_observations_review_decision",
        ),
        CheckConstraint(
            "verification_status IN ('pending','qualified','rejected','invalidated')",
            name="ck_teacher_observations_verification_status",
        ),
        UniqueConstraint(
            "verification_event_id", name="uq_teacher_observations_verification_event"
        ),
        UniqueConstraint(
            "verification_qualification_id",
            name="uq_teacher_observations_verification_qualification",
        ),
        Index("ix_teacher_observations_course_student", "course_id", "student_id", "created_at"),
        Index("ix_teacher_observations_course_status", "course_id", "qualification_status"),
        Index("ix_teacher_observations_class_status", "class_id", "qualification_status"),
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
    physical_page: Mapped[int | None] = mapped_column(Integer)
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


class ParsedPage(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """单页解析提交标记，供持久任务在重试时从检查点恢复。"""

    __tablename__ = "parsed_pages"

    material_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("material_versions.id"), nullable=False
    )
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    physical_page: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed", server_default="completed"
    )
    object_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint("status IN ('completed','failed')", name="ck_parsed_pages_status"),
        CheckConstraint("physical_page >= 1", name="ck_parsed_pages_physical_page"),
        UniqueConstraint(
            "material_version_id",
            "parser_version",
            "physical_page",
            name="uq_parsed_pages_version_parser_page",
        ),
        Index("ix_parsed_pages_version_status", "material_version_id", "status", "physical_page"),
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
    domain_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("domain_releases.id", ondelete="RESTRICT")
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
        Index("ix_retrieval_units_domain_release", "domain_release_id"),
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


class CourseReleaseAssignment(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """班级当前课程版本指派；历史换版记录保留，不回写运行快照。"""

    __tablename__ = "course_release_assignments"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="RESTRICT"), nullable=False
    )
    course_release_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    assigned_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    closed_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','closed','revoked')", name="ck_course_release_assignments_status"
        ),
        UniqueConstraint("supersedes_id", name="uq_course_release_assignments_supersedes"),
        Index(
            "uq_course_release_assignments_active_class",
            "class_id",
            unique=True,
            postgresql_where=sql_text("status = 'active'"),
        ),
        Index("ix_course_release_assignments_course", "course_id", "class_id", "assigned_at"),
    )


class RubricVersion(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """绑定不可变题目版本的确定性 Rubric 版本。"""

    __tablename__ = "rubric_versions"

    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    max_score: Mapped[float] = mapped_column(nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        UniqueConstraint("question_version_id", "version_no", name="uq_rubric_versions_no"),
        CheckConstraint("version_no >= 1", name="ck_rubric_versions_version"),
        CheckConstraint("max_score > 0", name="ck_rubric_versions_max_score"),
        CheckConstraint(
            "status IN ('draft','approved','retired')", name="ck_rubric_versions_status"
        ),
        Index("ix_rubric_versions_question_status", "question_version_id", "status"),
    )


class QuestionPurposeApproval(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    """针对具体题目版本与用途的追加式人工资格决定。"""

    __tablename__ = "question_purpose_approvals"

    question_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("question_versions.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    __table_args__ = (
        CheckConstraint("purpose IN ('practice','formal')", name="ck_question_purpose_approval"),
        CheckConstraint("decision IN ('approved','revoked')", name="ck_question_purpose_decision"),
        Index(
            "ix_question_purpose_approvals_latest",
            "question_version_id",
            "purpose",
            "created_at",
        ),
    )


class TeachingActivity(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """课程活动定义的不可变版本记录。"""

    __tablename__ = "teaching_activity_versions"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    activity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("teaching_activity_versions.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint(
            "course_id", "activity_key", "version_no", name="uq_teaching_activity_version"
        ),
        CheckConstraint("version_no >= 1", name="ck_teaching_activity_version_no"),
        CheckConstraint(
            "status IN ('draft','ready','published','deprecated')",
            name="ck_teaching_activity_status",
        ),
        Index("ix_teaching_activity_course_status", "course_id", "status", "activity_key"),
    )


class TeachingActivityRun(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """已冻结活动、课程版本与班级目标范围的运行实例。"""

    __tablename__ = "teaching_activity_runs"

    activity_version_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("teaching_activity_versions.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="RESTRICT"), nullable=False
    )
    course_release_assignment_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_release_assignments.id", ondelete="RESTRICT")
    )
    course_release_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("course_releases.id", ondelete="RESTRICT")
    )
    target_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    run_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned", server_default="planned"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_sha256: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','ready','active','paused','completed','cancelled')",
            name="ck_teaching_activity_runs_status",
        ),
        CheckConstraint(
            "(idempotency_key IS NULL AND request_sha256 IS NULL) OR "
            "(idempotency_key IS NOT NULL AND request_sha256 IS NOT NULL)",
            name="ck_teaching_activity_runs_idempotency",
        ),
        Index("ix_teaching_activity_runs_class_status", "class_id", "status", "created_at"),
        Index(
            "uq_teaching_activity_runs_idempotency",
            "course_id",
            "created_by",
            "idempotency_key",
            unique=True,
            postgresql_where=sql_text("idempotency_key IS NOT NULL"),
        ),
    )


class TeacherTimelineEvent(Base, ULIDPrimaryKeyMixin):
    """班级活动的追加式计划/实际时间线事件。"""

    __tablename__ = "teacher_timeline_events"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="RESTRICT"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(26), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str] = mapped_column(String(26), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("phase IN ('planned','actual')", name="ck_teacher_timeline_phase"),
        CheckConstraint(
            "subject_type IN ('activity','activity_run','intervention','annotation')",
            name="ck_teacher_timeline_subject",
        ),
        UniqueConstraint(
            "source_type", "source_id", "event_type", name="uq_teacher_timeline_source"
        ),
        Index("ix_teacher_timeline_class_time", "class_id", "occurred_at", "id"),
    )


class TeacherAnnotation(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    """教师 Scope 内的内容 overlay，不回写原始证据或 Domain canonical。"""

    __tablename__ = "teacher_annotations"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("course_classes.id", ondelete="RESTRICT"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(26), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="teacher_only", server_default="teacher_only"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    annotation: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('activity','evidence','knowledge_point','intervention')",
            name="ck_teacher_annotations_target",
        ),
        CheckConstraint(
            "visibility IN ('teacher_only','student_visible')",
            name="ck_teacher_annotations_visibility",
        ),
        CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_teacher_annotations_status"
        ),
        Index("ix_teacher_annotations_class_target", "class_id", "target_type", "target_id"),
    )
