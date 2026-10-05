"""make privacy deletion requests durable and recoverable

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint("ck_privacy_deletion_status", "privacy_deletion_requests", type_="check")
    op.create_check_constraint(
        "ck_privacy_deletion_status",
        "privacy_deletion_requests",
        "status IN ('queued', 'running', 'failed', 'completed_with_retention')",
    )
    op.alter_column(
        "privacy_deletion_requests",
        "completed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column(
        "privacy_deletion_requests",
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "privacy_deletion_requests",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("privacy_deletion_requests", "attempt_count", server_default=None)
    op.add_column(
        "privacy_deletion_requests",
        sa.Column("retryable", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("privacy_deletion_requests", "retryable", server_default=None)
    op.add_column(
        "privacy_deletion_requests",
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_privacy_deletion_requests_status_requested",
        "privacy_deletion_requests",
        ["status", "requested_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    unfinished = connection.execute(
        sa.text(
            "SELECT count(*) FROM privacy_deletion_requests "
            "WHERE status <> 'completed_with_retention'"
        )
    ).scalar_one()
    if unfinished:
        raise RuntimeError("Cannot downgrade while privacy deletion jobs are unfinished")
    op.drop_index(
        "ix_privacy_deletion_requests_status_requested",
        table_name="privacy_deletion_requests",
    )
    op.drop_column("privacy_deletion_requests", "last_error_code")
    op.drop_column("privacy_deletion_requests", "retryable")
    op.drop_column("privacy_deletion_requests", "attempt_count")
    op.drop_column("privacy_deletion_requests", "requested_at")
    op.alter_column(
        "privacy_deletion_requests",
        "completed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_constraint("ck_privacy_deletion_status", "privacy_deletion_requests", type_="check")
    op.create_check_constraint(
        "ck_privacy_deletion_status",
        "privacy_deletion_requests",
        "status IN ('completed_with_retention')",
    )
