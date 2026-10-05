"""clarify that privacy receipts count all processing actions

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "privacy_deletion_requests",
        "deleted_counts",
        new_column_name="processed_counts",
    )


def downgrade() -> None:
    op.alter_column(
        "privacy_deletion_requests",
        "processed_counts",
        new_column_name="deleted_counts",
    )
