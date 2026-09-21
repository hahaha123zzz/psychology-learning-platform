"""multimodal textbook RAG V3 object contracts

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("material_versions", sa.Column("canonical_pdf_key", sa.String(512)))
    op.add_column("material_versions", sa.Column("render_manifest", sa.JSON()))
    op.add_column("material_versions", sa.Column("render_version", sa.String(50)))
    op.add_column("material_versions", sa.Column("pipeline_version", sa.String(50)))
    op.add_column(
        "material_versions",
        sa.Column("quality_gate_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_material_versions_quality_gate",
        "material_versions",
        "quality_gate_status IN ('pending','blocked','approved')",
    )
    op.create_table(
        "object_assets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("knowledge_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id")),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("physical_page", sa.Integer),
        sa.Column("bbox", sa.JSON),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("render_version", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "asset_type IN ('canonical_pdf','page_image','object_crop','parser_payload')",
            name="ck_object_assets_type",
        ),
        sa.CheckConstraint(
            "status IN ('ready','failed','removed')", name="ck_object_assets_status"
        ),
        sa.UniqueConstraint(
            "material_version_id", "object_key", name="uq_object_assets_version_key"
        ),
    )
    op.create_index(
        "ix_object_assets_version_page", "object_assets", ["material_version_id", "physical_page"]
    )
    op.create_table(
        "object_representations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "knowledge_object_id",
            sa.String(26),
            sa.ForeignKey("knowledge_objects.id"),
            nullable=False,
        ),
        sa.Column("representation_type", sa.String(40), nullable=False),
        sa.Column("text_content", sa.Text),
        sa.Column("structured_content", sa.JSON),
        sa.Column("provider", sa.String(50)),
        sa.Column("model", sa.String(100)),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "representation_type IN "
            "('ocr','caption','table_json','table_markdown','latex',"
            "'semantic_description','retrieval_text')",
            name="ck_object_representations_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','ready','failed','superseded')",
            name="ck_object_representations_status",
        ),
        sa.UniqueConstraint(
            "knowledge_object_id",
            "representation_type",
            "generator_version",
            "source_hash",
            name="uq_object_representations_source",
        ),
    )
    op.create_index(
        "ix_object_representations_object",
        "object_representations",
        ["knowledge_object_id", "representation_type"],
    )
    op.create_table(
        "object_relations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "source_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id"), nullable=False
        ),
        sa.Column(
            "target_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id"), nullable=False
        ),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "relation_type IN "
            "('parent_of','previous','next','caption_of','references',"
            "'continues_on','explains','same_table','same_figure')",
            name="ck_object_relations_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')", name="ck_object_relations_review"
        ),
        sa.UniqueConstraint(
            "source_object_id", "target_object_id", "relation_type", name="uq_object_relations_edge"
        ),
    )
    op.create_index(
        "ix_object_relations_source", "object_relations", ["source_object_id", "relation_type"]
    )
    op.create_index(
        "ix_object_relations_target", "object_relations", ["target_object_id", "relation_type"]
    )
    op.create_table(
        "retrieval_units",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "source_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id"), nullable=False
        ),
        sa.Column("parent_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id")),
        sa.Column("representation_id", sa.String(26), sa.ForeignKey("object_representations.id")),
        sa.Column("unit_type", sa.String(30), nullable=False),
        sa.Column("channel_hint", sa.String(20), nullable=False),
        sa.Column("char_start", sa.Integer),
        sa.Column("char_end", sa.Integer),
        sa.Column("bbox", sa.JSON),
        sa.Column("text_content", sa.Text),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("build_strategy", sa.String(50), nullable=False),
        sa.Column("build_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "unit_type IN "
            "('text_child','table','table_row','table_column','table_cells',"
            "'image','page','equation')",
            name="ck_retrieval_units_type",
        ),
        sa.CheckConstraint(
            "channel_hint IN ('sparse','dense','visual','multi_vector')",
            name="ck_retrieval_units_channel",
        ),
        sa.CheckConstraint(
            "status IN ('queued','ready','failed','superseded')", name="ck_retrieval_units_status"
        ),
        sa.UniqueConstraint(
            "source_object_id",
            "representation_id",
            "unit_type",
            "build_strategy",
            "build_version",
            "content_hash",
            name="uq_retrieval_units_build",
        ),
    )
    op.create_index(
        "ix_retrieval_units_version_type", "retrieval_units", ["material_version_id", "unit_type"]
    )
    op.create_index("ix_retrieval_units_source", "retrieval_units", ["source_object_id"])
    op.create_table(
        "retrieval_index_entries",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "retrieval_unit_id", sa.String(26), sa.ForeignKey("retrieval_units.id"), nullable=False
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("dimension", sa.Integer),
        sa.Column("index_version", sa.String(50), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("metadata_json", sa.JSON),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "channel IN ('sparse','dense','visual','multi_vector')",
            name="ck_retrieval_index_entries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('queued','building','ready','failed','superseded')",
            name="ck_retrieval_index_entries_status",
        ),
        sa.UniqueConstraint(
            "retrieval_unit_id",
            "channel",
            "provider",
            "model",
            "model_version",
            "index_version",
            "source_hash",
            name="uq_retrieval_index_entries_version",
        ),
    )
    op.create_index(
        "ix_retrieval_index_entries_lookup",
        "retrieval_index_entries",
        ["channel", "index_version", "status"],
    )
    op.create_table(
        "parse_review_issues",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "material_version_id",
            sa.String(26),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("knowledge_object_id", sa.String(26), sa.ForeignKey("knowledge_objects.id")),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("detail", sa.JSON),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text),
        sa.Column("resolved_by", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "severity IN ('blocking','warning','info')", name="ck_parse_review_issues_severity"
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved','ignored')", name="ck_parse_review_issues_status"
        ),
        sa.UniqueConstraint(
            "material_version_id",
            "knowledge_object_id",
            "code",
            "status",
            name="uq_parse_review_issues_open",
        ),
    )
    op.create_index(
        "ix_parse_review_issues_version",
        "parse_review_issues",
        ["material_version_id", "severity", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_parse_review_issues_version", table_name="parse_review_issues")
    op.drop_table("parse_review_issues")
    op.drop_index("ix_retrieval_index_entries_lookup", table_name="retrieval_index_entries")
    op.drop_table("retrieval_index_entries")
    op.drop_index("ix_retrieval_units_source", table_name="retrieval_units")
    op.drop_index("ix_retrieval_units_version_type", table_name="retrieval_units")
    op.drop_table("retrieval_units")
    op.drop_index("ix_object_relations_target", table_name="object_relations")
    op.drop_index("ix_object_relations_source", table_name="object_relations")
    op.drop_table("object_relations")
    op.drop_index("ix_object_representations_object", table_name="object_representations")
    op.drop_table("object_representations")
    op.drop_index("ix_object_assets_version_page", table_name="object_assets")
    op.drop_table("object_assets")
    op.drop_constraint("ck_material_versions_quality_gate", "material_versions", type_="check")
    op.drop_column("material_versions", "quality_gate_status")
    op.drop_column("material_versions", "pipeline_version")
    op.drop_column("material_versions", "render_version")
    op.drop_column("material_versions", "render_manifest")
    op.drop_column("material_versions", "canonical_pdf_key")
