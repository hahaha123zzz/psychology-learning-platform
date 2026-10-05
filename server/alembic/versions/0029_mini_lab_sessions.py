"""add server-authoritative mini lab sessions

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mini_lab_sessions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("lab_key", sa.String(length=80), nullable=False),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column("phase", sa.String(length=20), server_default="intro", nullable=False),
        sa.Column("trial_data", sa.JSON(), nullable=False),
        sa.Column("derived_measure", sa.JSON(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','invalidated')",
            name="ck_mini_lab_sessions_status",
        ),
        sa.CheckConstraint(
            "phase IN ('intro','predict','run','inspect','explain','summary')",
            name="ck_mini_lab_sessions_phase",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mini_lab_sessions_course_id", "mini_lab_sessions", ["course_id"], unique=False
    )
    op.create_index(
        "ix_mini_lab_sessions_user_course",
        "mini_lab_sessions",
        ["user_id", "course_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mini_lab_sessions_user_course", table_name="mini_lab_sessions")
    op.drop_index("ix_mini_lab_sessions_course_id", table_name="mini_lab_sessions")
    op.drop_table("mini_lab_sessions")
