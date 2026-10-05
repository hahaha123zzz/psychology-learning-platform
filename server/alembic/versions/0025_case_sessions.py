"""add case reasoning sessions

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("case_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("case_snapshot", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("outcome", sa.JSON()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('active','completed','abandoned')", name="ck_case_sessions_status"
        ),
    )
    op.create_index(
        "ix_case_sessions_user_course", "case_sessions", ["user_id", "course_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_case_sessions_user_course", table_name="case_sessions")
    op.drop_table("case_sessions")
