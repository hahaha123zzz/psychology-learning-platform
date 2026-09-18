"""jobs table and material version status extension

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_material_versions_status", "material_versions", type_="check"
    )
    op.create_check_constraint(
        "ck_material_versions_status",
        "material_versions",
        "status IN ('uploading','uploaded','failed','parsing','parsed','removed')",
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stage", sa.String(100)),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("retryable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_jobs_status",
        ),
        sa.UniqueConstraint("kind", "idempotency_key", name="uq_jobs_kind_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_constraint(
        "ck_material_versions_status", "material_versions", type_="check"
    )
    op.create_check_constraint(
        "ck_material_versions_status",
        "material_versions",
        "status IN ('uploading','uploaded','failed','removed')",
    )
