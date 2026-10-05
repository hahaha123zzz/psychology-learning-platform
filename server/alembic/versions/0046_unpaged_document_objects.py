"""allow document objects without verified physical-page coordinates

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "knowledge_objects",
        "physical_page",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "knowledge_chunks",
        "physical_page",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    unpaged_objects = connection.execute(
        sa.text("SELECT count(*) FROM knowledge_objects WHERE physical_page IS NULL")
    ).scalar_one()
    unpaged_chunks = connection.execute(
        sa.text("SELECT count(*) FROM knowledge_chunks WHERE physical_page IS NULL")
    ).scalar_one()
    if unpaged_objects or unpaged_chunks:
        raise RuntimeError(
            "Cannot downgrade while knowledge objects or chunks have no verified physical page"
        )
    op.alter_column(
        "knowledge_chunks",
        "physical_page",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "knowledge_objects",
        "physical_page",
        existing_type=sa.Integer(),
        nullable=False,
    )
