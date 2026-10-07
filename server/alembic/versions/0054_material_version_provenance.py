"""add version-scoped source provenance and review state

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("material_versions", sa.Column("source_title", sa.String(length=300)))
    op.add_column("material_versions", sa.Column("publisher", sa.String(length=200)))
    op.add_column("material_versions", sa.Column("content_author", sa.String(length=200)))
    op.add_column("material_versions", sa.Column("edition", sa.String(length=100)))
    op.add_column("material_versions", sa.Column("source_url", sa.String(length=1000)))
    op.add_column("material_versions", sa.Column("license", sa.String(length=200)))
    op.add_column(
        "material_versions", sa.Column("course_resource_role", sa.String(length=40))
    )
    op.add_column(
        "material_versions",
        sa.Column(
            "provenance_status",
            sa.String(length=20),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column(
        "material_versions",
        sa.Column("provenance_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "material_versions",
        sa.Column("provenance_submitted_by", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "material_versions",
        sa.Column("provenance_reviewed_by", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "material_versions",
        sa.Column("provenance_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "material_versions", sa.Column("provenance_review_note", sa.String(length=1000))
    )
    op.create_foreign_key(
        "fk_material_versions_provenance_submitted_by",
        "material_versions",
        "users",
        ["provenance_submitted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_material_versions_provenance_reviewed_by",
        "material_versions",
        "users",
        ["provenance_reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_material_versions_provenance_status",
        "material_versions",
        "provenance_status IN ('unreviewed','verified','rejected')",
    )
    op.create_check_constraint(
        "ck_material_versions_course_resource_role",
        "material_versions",
        "course_resource_role IS NULL OR course_resource_role IN "
        "('course_textbook','supplementary_resource')",
    )
    op.create_check_constraint(
        "ck_material_versions_provenance_version",
        "material_versions",
        "provenance_version >= 1",
    )
    op.create_check_constraint(
        "ck_material_versions_provenance_review",
        "material_versions",
        "(provenance_status = 'unreviewed' AND provenance_reviewed_by IS NULL "
        "AND provenance_reviewed_at IS NULL) OR "
        "(provenance_status IN ('verified','rejected') AND provenance_reviewed_by IS NOT NULL "
        "AND provenance_reviewed_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_material_versions_provenance_review", "material_versions", type_="check")
    op.drop_constraint(
        "ck_material_versions_provenance_version", "material_versions", type_="check"
    )
    op.drop_constraint(
        "ck_material_versions_course_resource_role", "material_versions", type_="check"
    )
    op.drop_constraint("ck_material_versions_provenance_status", "material_versions", type_="check")
    op.drop_constraint(
        "fk_material_versions_provenance_reviewed_by", "material_versions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_material_versions_provenance_submitted_by", "material_versions", type_="foreignkey"
    )
    op.drop_column("material_versions", "provenance_review_note")
    op.drop_column("material_versions", "provenance_reviewed_at")
    op.drop_column("material_versions", "provenance_reviewed_by")
    op.drop_column("material_versions", "provenance_submitted_by")
    op.drop_column("material_versions", "provenance_status")
    op.drop_column("material_versions", "provenance_version")
    op.drop_column("material_versions", "license")
    op.drop_column("material_versions", "course_resource_role")
    op.drop_column("material_versions", "source_url")
    op.drop_column("material_versions", "edition")
    op.drop_column("material_versions", "content_author")
    op.drop_column("material_versions", "publisher")
    op.drop_column("material_versions", "source_title")
