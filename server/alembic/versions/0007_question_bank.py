"""question bank, assessments, attempts

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.String(26)),
        sa.Column("origin", sa.String(20), nullable=False, server_default="teacher"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts_cols(),
        sa.CheckConstraint(
            "status IN ('draft','approved','published','rejected','archived')",
            name="ck_questions_status",
        ),
        sa.CheckConstraint("origin IN ('teacher','agent')", name="ck_questions_origin"),
    )
    op.create_index("ix_questions_course_id", "questions", ["course_id"])
    op.create_table(
        "question_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("question_id", sa.String(26), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("stem", sa.Text, nullable=False),
        sa.Column("options", sa.JSON),
        sa.Column("answer", sa.JSON),
        sa.Column("rubric", sa.Text),
        sa.Column("explanation", sa.Text),
        sa.Column("difficulty", sa.Integer, nullable=False),
        sa.Column("knowledge_point_ids", sa.JSON),
        sa.Column("evidence_ids", sa.JSON),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("question_id", "version_no", name="uq_question_versions_no"),
        sa.CheckConstraint(
            "type IN ('single','multiple','true_false','short_answer','essay')",
            name="ck_question_versions_type",
        ),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_question_versions_difficulty"),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True)),
        sa.Column("closes_at", sa.DateTime(timezone=True)),
        sa.Column(
            "ai_policy", sa.String(30), nullable=False, server_default="full_after_submit"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts_cols(),
        sa.CheckConstraint(
            "ai_policy IN ('disabled','direction_only','full_after_submit')",
            name="ck_assessments_ai_policy",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','closed')", name="ck_assessments_status"
        ),
    )
    op.create_index("ix_assessments_course_id", "assessments", ["course_id"])
    op.create_table(
        "assessment_items",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "assessment_id", sa.String(26), sa.ForeignKey("assessments.id"), nullable=False
        ),
        sa.Column(
            "question_version_id",
            sa.String(26),
            sa.ForeignKey("question_versions.id"),
            nullable=False,
        ),
        sa.Column("points", sa.Float, nullable=False, server_default="1"),
        sa.Column("order_no", sa.Integer, nullable=False),
        sa.UniqueConstraint("assessment_id", "question_version_id", name="uq_assessment_items"),
    )
    op.create_table(
        "attempts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("assessment_id", sa.String(26), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Float),
        sa.Column("grading_status", sa.String(20)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("coach_hints", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts_cols(),
        sa.CheckConstraint(
            "status IN ('in_progress','submitted','graded')", name="ck_attempts_status"
        ),
    )
    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("attempt_id", sa.String(26), sa.ForeignKey("attempts.id"), nullable=False),
        sa.Column(
            "question_version_id",
            sa.String(26),
            sa.ForeignKey("question_versions.id"),
            nullable=False,
        ),
        sa.Column("response", sa.JSON),
        sa.Column("client_saved_at", sa.DateTime(timezone=True)),
        sa.Column("is_correct", sa.Boolean),
        sa.Column("points_earned", sa.Float),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts_cols(),
        sa.UniqueConstraint("attempt_id", "question_version_id", name="uq_attempt_answers"),
    )


def downgrade() -> None:
    op.drop_table("attempt_answers")
    op.drop_table("attempts")
    op.drop_table("assessment_items")
    op.drop_index("ix_assessments_course_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_table("question_versions")
    op.drop_index("ix_questions_course_id", table_name="questions")
    op.drop_table("questions")
