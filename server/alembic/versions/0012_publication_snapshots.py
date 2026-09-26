"""add immutable publication snapshots

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publication_snapshots",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("material_id", sa.String(26), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("parse_job_id", sa.String(26), sa.ForeignKey("jobs.id")),
        sa.Column("index_job_id", sa.String(26), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("embedding_version", sa.String(100), nullable=False),
        sa.Column("published_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_publication_snapshots_current",
        "publication_snapshots",
        ["material_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_publication_snapshots_version",
        "publication_snapshots",
        ["material_version_id", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_publication_snapshots_version", table_name="publication_snapshots")
    op.drop_index("uq_publication_snapshots_current", table_name="publication_snapshots")
    op.drop_table("publication_snapshots")
