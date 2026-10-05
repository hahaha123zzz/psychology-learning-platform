"""Add minimized wrong-answer traces and question quality feedback.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wrong_answer_traces",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("attempt_id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("question_version_id", sa.String(length=26), nullable=False),
        sa.Column("answer_present", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "question_version_id",
            name="uq_wrong_answer_trace_attempt_question",
        ),
    )
    op.create_index(
        "ix_wrong_answer_traces_user_course",
        "wrong_answer_traces",
        ["user_id", "course_id", "created_at"],
    )

    op.create_table(
        "question_quality_feedback",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("attempt_id", sa.String(length=26), nullable=False),
        sa.Column("question_version_id", sa.String(length=26), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("resolution_action", sa.String(length=20)),
        sa.Column("resolution_rationale", sa.Text()),
        sa.Column("resolved_by", sa.String(length=26)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('answer_key','ambiguous','outdated','other')",
            name="ck_question_quality_feedback_category",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected','invalidated')",
            name="ck_question_quality_feedback_status",
        ),
        sa.CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN ('accept','reject','invalidate')",
            name="ck_question_quality_feedback_action",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "attempt_id",
            "question_version_id",
            name="uq_question_quality_feedback_attempt_question",
        ),
    )
    op.create_index(
        "ix_question_quality_feedback_course_status",
        "question_quality_feedback",
        ["course_id", "status", "created_at"],
    )
    op.create_index(
        "ix_question_quality_feedback_question",
        "question_quality_feedback",
        ["question_version_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_quality_feedback_question", table_name="question_quality_feedback")
    op.drop_index(
        "ix_question_quality_feedback_course_status", table_name="question_quality_feedback"
    )
    op.drop_table("question_quality_feedback")
    op.drop_index("ix_wrong_answer_traces_user_course", table_name="wrong_answer_traces")
    op.drop_table("wrong_answer_traces")
