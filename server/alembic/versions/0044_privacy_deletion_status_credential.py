"""allow a deleted account to verify its deletion receipt once offline

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "privacy_deletion_requests",
        sa.Column("status_credential_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "privacy_deletion_requests",
        sa.Column("status_credential_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_privacy_deletion_status_credential_hash",
        "privacy_deletion_requests",
        ["status_credential_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_privacy_deletion_status_credential_hash",
        table_name="privacy_deletion_requests",
    )
    op.drop_column("privacy_deletion_requests", "status_credential_expires_at")
    op.drop_column("privacy_deletion_requests", "status_credential_hash")
