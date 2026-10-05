"""persist immutable textbook evidence pointers

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_pointers",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("material_id", sa.String(26), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "source_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id")
        ),
        sa.Column("retrieval_unit_id", sa.String(26)),
        sa.Column("material_title", sa.String(200), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_sha256", sa.String(64), nullable=False),
        sa.Column("chapter_path", sa.String(1000)),
        sa.Column("physical_page", sa.Integer()),
        sa.Column("reading_order", sa.Integer()),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column(
            "coordinate_space",
            sa.String(50),
            nullable=False,
            server_default="pdf_user_bottom_left",
        ),
        sa.Column("bbox", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "physical_page IS NULL OR physical_page >= 1", name="ck_evidence_pointer_page"
        ),
        sa.CheckConstraint(
            "coordinate_space IN ('pdf_user_bottom_left','unavailable')",
            name="ck_evidence_pointer_coordinate_space",
        ),
    )
    op.create_index(
        "ix_evidence_pointers_course_created", "evidence_pointers", ["course_id", "created_at"]
    )
    op.create_index(
        "ix_evidence_pointers_version_object",
        "evidence_pointers",
        ["material_version_id", "source_object_id"],
    )
    op.add_column("evidence_tickets", sa.Column("pointer_id", sa.String(26)))
    op.create_foreign_key(
        "fk_evidence_tickets_pointer_id_evidence_pointers",
        "evidence_tickets",
        "evidence_pointers",
        ["pointer_id"],
        ["id"],
    )
    op.create_index("ix_evidence_tickets_pointer_id", "evidence_tickets", ["pointer_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_tickets_pointer_id", table_name="evidence_tickets")
    op.drop_constraint(
        "fk_evidence_tickets_pointer_id_evidence_pointers",
        "evidence_tickets",
        type_="foreignkey",
    )
    op.drop_column("evidence_tickets", "pointer_id")
    op.drop_index("ix_evidence_pointers_version_object", table_name="evidence_pointers")
    op.drop_index("ix_evidence_pointers_course_created", table_name="evidence_pointers")
    op.drop_table("evidence_pointers")
