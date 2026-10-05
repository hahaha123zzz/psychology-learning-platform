"""Prevent duplicate active role assignments across nullable scopes.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            """
            SELECT user_id, role, scope_type, COALESCE(scope_id, '') AS normalized_scope
            FROM role_assignments
            WHERE status = 'active'
            GROUP BY user_id, role, scope_type, COALESCE(scope_id, '')
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "duplicate active role assignments must be reviewed before applying migration 0039"
        )
    op.create_index(
        "uq_role_assignments_active_scope",
        "role_assignments",
        ["user_id", "role", "scope_type", sa.text("COALESCE(scope_id, '')")],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_role_assignments_active_scope", table_name="role_assignments")
