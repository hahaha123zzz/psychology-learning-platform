"""add explicit role assignments and resource scopes

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.String(26)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("granted_by", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('student','teacher','assistant','course_designer',"
            "'course_publisher','admin')",
            name="ck_role_assignments_role",
        ),
        sa.CheckConstraint(
            "scope_type IN ('platform','course','class')",
            name="ck_role_assignments_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'platform' AND scope_id IS NULL) OR "
            "(scope_type IN ('course','class') AND scope_id IS NOT NULL)",
            name="ck_role_assignments_scope_id",
        ),
        sa.CheckConstraint("status IN ('active','revoked')", name="ck_role_assignments_status"),
        sa.UniqueConstraint(
            "user_id", "role", "scope_type", "scope_id", name="uq_role_assignments_scope"
        ),
    )
    op.create_index("ix_role_assignments_user_status", "role_assignments", ["user_id", "status"])
    op.create_index(
        "ix_role_assignments_scope_status",
        "role_assignments",
        ["scope_type", "scope_id", "status"],
    )
def downgrade() -> None:
    op.drop_index("ix_role_assignments_scope_status", table_name="role_assignments")
    op.drop_index("ix_role_assignments_user_status", table_name="role_assignments")
    op.drop_table("role_assignments")
