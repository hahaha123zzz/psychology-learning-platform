"""materials and material versions

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("material_type", sa.String(30), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_version_id", sa.String(26)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "material_type IN ('textbook','slides','handout','exercise','reference','other')",
            name="ck_materials_type",
        ),
        sa.CheckConstraint(
            "visibility IN ('draft','published')", name="ck_materials_visibility"
        ),
        sa.CheckConstraint(
            "status IN ('active','archived','deleted')", name="ck_materials_status"
        ),
    )
    op.create_index("ix_materials_course", "materials", ["course_id", "status"])
    op.create_table(
        "material_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("material_id", sa.String(26), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploading"),
        sa.Column("object_key", sa.String(512)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("content_type", sa.String(100)),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("material_id", "version_no", name="uq_material_versions_no"),
        sa.CheckConstraint(
            "status IN ('uploading','uploaded','failed','removed')",
            name="ck_material_versions_status",
        ),
    )
    op.create_index("ix_material_versions_sha256", "material_versions", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_material_versions_sha256", table_name="material_versions")
    op.drop_table("material_versions")
    op.drop_index("ix_materials_course", table_name="materials")
    op.drop_table("materials")
