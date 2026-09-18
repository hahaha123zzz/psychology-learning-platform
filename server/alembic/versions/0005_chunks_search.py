"""knowledge chunks with pgvector, evidence tickets

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("course_id", sa.String(26), nullable=False, index=True),
        sa.Column("chapter_object_id", sa.String(26)),
        sa.Column("chapter_path", sa.String(100), nullable=False, server_default=""),
        sa.Column("physical_page", sa.Integer, nullable=False),
        sa.Column("reading_order", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding_version", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        f"ALTER TABLE knowledge_chunks ADD COLUMN embedding vector({EMBEDDING_DIM})"
    )
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ADD COLUMN text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_tsv ON knowledge_chunks USING GIN (text_tsv)"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_index(
        "ix_knowledge_chunks_version_order",
        "knowledge_chunks",
        ["material_version_id", "reading_order"],
    )
    op.create_table(
        "evidence_tickets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("chunk_id", sa.String(26), nullable=False, index=True),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("material_version_id", sa.String(26), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("evidence_tickets")
    op.drop_index(
        "ix_knowledge_chunks_version_order", table_name="knowledge_chunks"
    )
    op.execute("DROP TABLE knowledge_chunks")
    op.execute("DROP EXTENSION IF EXISTS vector")
