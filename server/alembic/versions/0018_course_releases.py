"""add immutable course release manifests

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_releases",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(26),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_by", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("deprecated_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("course_id", "version_no", name="uq_course_releases_course_version"),
        sa.CheckConstraint(
            "status IN ('draft','published','deprecated')", name="ck_course_releases_status"
        ),
    )
    op.create_index(
        "ix_course_releases_course_status",
        "course_releases",
        ["course_id", "status", "version_no"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_releases_course_status", table_name="course_releases")
    op.drop_table("course_releases")
