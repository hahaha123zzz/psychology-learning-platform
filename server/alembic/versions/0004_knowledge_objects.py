"""knowledge objects and material version quality fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("material_versions", sa.Column("page_count", sa.Integer))
    op.add_column("material_versions", sa.Column("quality_report", sa.JSON))
    op.create_table(
        "knowledge_objects",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("chapter_path", sa.String(100), nullable=False, server_default=""),
        sa.Column("parent_id", sa.String(26)),
        sa.Column("physical_page", sa.Integer, nullable=False),
        sa.Column("printed_page", sa.Integer),
        sa.Column("reading_order", sa.Integer, nullable=False),
        sa.Column("bbox", sa.JSON),
        sa.Column("raw_content", sa.Text, nullable=False, server_default=""),
        sa.Column("normalized_content", sa.Text),
        sa.Column("parser", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("override", sa.JSON),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "type IN ('chapter','paragraph','figure','table','formula')",
            name="ck_knowledge_objects_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected','corrected')",
            name="ck_knowledge_objects_review",
        ),
    )
    op.create_index(
        "ix_knowledge_objects_version_order",
        "knowledge_objects",
        ["material_version_id", "reading_order"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_objects_version_order", table_name="knowledge_objects"
    )
    op.drop_table("knowledge_objects")
    op.drop_column("material_versions", "quality_report")
    op.drop_column("material_versions", "page_count")
