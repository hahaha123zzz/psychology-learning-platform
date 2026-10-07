"""persist versioned student review drafts

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("review_tasks", sa.Column("response_draft", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_tasks", "response_draft")
