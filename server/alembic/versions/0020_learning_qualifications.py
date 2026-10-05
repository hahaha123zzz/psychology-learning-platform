"""add deterministic learning qualification records

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_qualifications",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(26),
            sa.ForeignKey("learning_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("event_id", name="uq_learning_qualifications_event"),
        sa.CheckConstraint(
            "status IN ('qualified','rejected','invalidated')",
            name="ck_learning_qualifications_status",
        ),
    )
    op.create_index(
        "ix_learning_qualifications_user_course",
        "learning_qualifications",
        ["user_id", "course_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_qualifications_user_course", table_name="learning_qualifications"
    )
    op.drop_table("learning_qualifications")
