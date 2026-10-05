"""add immutable raw learning events

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(128)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qualification_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("qualification_reason", sa.String(500)),
        sa.Column("qualified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "event_key", name="uq_learning_events_user_key"),
        sa.CheckConstraint(
            "event_type IN ('task_viewed','answer_submitted','tutor_responded',"
            "'lab_trial_completed','feedback_submitted')",
            name="ck_learning_events_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('tutor','assessment','practice','lab','system')",
            name="ck_learning_events_source",
        ),
        sa.CheckConstraint(
            "qualification_status IN ('pending','qualified','rejected','invalidated')",
            name="ck_learning_events_qualification",
        ),
    )
    op.create_index(
        "ix_learning_events_user_course_time",
        "learning_events",
        ["user_id", "course_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_events_user_course_time", table_name="learning_events")
    op.drop_table("learning_events")
