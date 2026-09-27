"""add durable native PDF page parse checkpoints

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "parsed_pages",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("physical_page", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("object_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("asset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("error", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("status IN ('completed','failed')", name="ck_parsed_pages_status"),
        sa.CheckConstraint("physical_page >= 1", name="ck_parsed_pages_physical_page"),
        sa.UniqueConstraint(
            "material_version_id",
            "parser_version",
            "physical_page",
            name="uq_parsed_pages_version_parser_page",
        ),
    )
    op.create_index(
        "ix_parsed_pages_version_status",
        "parsed_pages",
        ["material_version_id", "status", "physical_page"],
    )


def downgrade() -> None:
    op.drop_index("ix_parsed_pages_version_status", table_name="parsed_pages")
    op.drop_table("parsed_pages")
