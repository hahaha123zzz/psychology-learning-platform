"""add independent class members

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_members",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "class_id",
            sa.String(26),
            sa.ForeignKey("course_classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),
        sa.CheckConstraint("status IN ('active','removed')", name="ck_class_members_status"),
    )
    op.create_index("ix_class_members_class_status", "class_members", ["class_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_class_members_class_status", table_name="class_members")
    op.drop_table("class_members")
