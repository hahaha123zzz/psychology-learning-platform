"""add versioned teaching asset registry

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teaching_asset_versions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("release_id", sa.String(length=26), nullable=True),
        sa.Column("asset_key", sa.String(length=100), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("fallback_text", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("allowed_actions", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=26), nullable=False),
        sa.Column("published_by", sa.String(length=26), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "template IN ('explanation','comparison','variable_map','table','focus')",
            name="ck_teaching_asset_template",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_teaching_asset_status"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["release_id"], ["course_releases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id", "asset_key", "version_no", name="uq_teaching_asset_course_key_version"
        ),
    )
    op.create_index(
        "ix_teaching_asset_course_status",
        "teaching_asset_versions",
        ["course_id", "status", "asset_key", "version_no"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_teaching_asset_course_status", table_name="teaching_asset_versions")
    op.drop_table("teaching_asset_versions")
