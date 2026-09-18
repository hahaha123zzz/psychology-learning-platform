"""branch chat fields, review tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("parent_session_id", sa.String(26)))
    op.add_column(
        "chat_sessions",
        sa.Column(
            "is_branch", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column("chat_sessions", sa.Column("branch_source_turn_id", sa.String(26)))
    op.add_column("chat_sessions", sa.Column("branch_selection", sa.Text))
    op.add_column("chat_sessions", sa.Column("merge_note", sa.Text))
    op.create_index(
        "ix_chat_sessions_parent_session_id", "chat_sessions", ["parent_session_id"]
    )
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("question_version_id", sa.String(26), nullable=False),
        sa.Column("source_attempt_id", sa.String(26)),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason IN ('wrong_answer','review_schedule')", name="ck_review_tasks_reason"
        ),
        sa.CheckConstraint(
            "status IN ('pending','done','dismissed')", name="ck_review_tasks_status"
        ),
    )
    op.create_index("ix_review_tasks_course_id", "review_tasks", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_review_tasks_course_id", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index(
        "ix_chat_sessions_parent_session_id", table_name="chat_sessions"
    )
    op.drop_column("chat_sessions", "merge_note")
    op.drop_column("chat_sessions", "branch_selection")
    op.drop_column("chat_sessions", "branch_source_turn_id")
    op.drop_column("chat_sessions", "is_branch")
    op.drop_column("chat_sessions", "parent_session_id")
