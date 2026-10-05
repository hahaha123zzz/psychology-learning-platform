"""add transactional outbox and consumer receipts

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("producer", sa.String(80), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.CheckConstraint("event_version > 0", name="ck_outbox_event_version_positive"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_attempt_count_nonnegative"),
    )
    op.create_index(
        "ix_outbox_events_pending", "outbox_events", ["published_at", "occurred_at", "id"]
    )
    op.create_index(
        "ix_outbox_events_type_occurred", "outbox_events", ["event_type", "occurred_at"]
    )
    op.create_table(
        "outbox_consumer_receipts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(26),
            sa.ForeignKey("outbox_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consumer_name", sa.String(120), nullable=False),
        sa.Column(
            "consumed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("event_id", "consumer_name", name="uq_outbox_consumer_event"),
    )
    op.create_index(
        "ix_outbox_receipts_consumer", "outbox_consumer_receipts", ["consumer_name", "consumed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_receipts_consumer", table_name="outbox_consumer_receipts")
    op.drop_table("outbox_consumer_receipts")
    op.drop_index("ix_outbox_events_type_occurred", table_name="outbox_events")
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events")
    op.drop_table("outbox_events")
