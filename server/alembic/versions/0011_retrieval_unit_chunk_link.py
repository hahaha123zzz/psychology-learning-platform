"""link legacy knowledge chunks to V3 retrieval units

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 历史合并块无法无歧义反向映射；下一次重建索引后由新构建器填充。
    op.add_column(
        "knowledge_chunks",
        sa.Column("source_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id")),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("retrieval_unit_id", sa.String(26), sa.ForeignKey("retrieval_units.id")),
    )
    op.create_index(
        "ix_knowledge_chunks_source_object", "knowledge_chunks", ["source_object_id"]
    )
    op.create_index(
        "ix_knowledge_chunks_retrieval_unit", "knowledge_chunks", ["retrieval_unit_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_retrieval_unit", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source_object", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "retrieval_unit_id")
    op.drop_column("knowledge_chunks", "source_object_id")
