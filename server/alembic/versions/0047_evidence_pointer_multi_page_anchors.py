"""persist all fixed-layout anchors for evidence pointers

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("evidence_pointers", sa.Column("anchors", sa.JSON(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    multi_page_pointers = connection.execute(
        sa.text(
            "SELECT count(*) FROM evidence_pointers "
            "WHERE anchors IS NOT NULL AND json_array_length(anchors) > 1"
        )
    ).scalar_one()
    if multi_page_pointers:
        raise RuntimeError("Cannot downgrade while multi-page evidence anchors exist")
    op.drop_column("evidence_pointers", "anchors")
