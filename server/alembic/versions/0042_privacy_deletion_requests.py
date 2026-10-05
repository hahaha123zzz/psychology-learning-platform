"""record privacy deletion outcomes and retention boundaries

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "privacy_deletion_requests",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("subject_user_id", sa.String(length=26), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("deleted_counts", sa.JSON(), nullable=False),
        sa.Column("retained_categories", sa.JSON(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('completed_with_retention')", name="ck_privacy_deletion_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_privacy_deletion_requests_subject_user_id",
        "privacy_deletion_requests",
        ["subject_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_privacy_deletion_requests_subject_user_id", table_name="privacy_deletion_requests"
    )
    op.drop_table("privacy_deletion_requests")
