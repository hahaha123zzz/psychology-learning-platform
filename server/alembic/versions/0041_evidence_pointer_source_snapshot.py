"""decouple persistent evidence pointers from reparsable objects

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL 使用默认命名，因为 0040 中该外键未显式命名。
    op.drop_constraint(
        "evidence_pointers_source_object_id_fkey",
        "evidence_pointers",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "evidence_pointers_source_object_id_fkey",
        "evidence_pointers",
        "knowledge_objects",
        ["source_object_id"],
        ["id"],
    )
