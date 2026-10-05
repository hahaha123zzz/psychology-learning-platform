"""add review verification qualification state

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_learning_events_source", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_source",
        "learning_events",
        "source_type IN ('tutor','assessment','practice','review','lab','system')",
    )
    op.add_column(
        "review_tasks",
        sa.Column(
            "qualification_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column("review_tasks", sa.Column("qualification_reason", sa.String(length=500)))
    op.create_check_constraint(
        "ck_review_tasks_qualification",
        "review_tasks",
        "qualification_status IN ('pending','qualified','rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_review_tasks_qualification", "review_tasks", type_="check")
    op.drop_column("review_tasks", "qualification_reason")
    op.drop_column("review_tasks", "qualification_status")
    op.drop_constraint("ck_learning_events_source", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_source",
        "learning_events",
        "source_type IN ('tutor','assessment','practice','lab','system')",
    )
