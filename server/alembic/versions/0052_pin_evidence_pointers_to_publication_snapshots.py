"""pin evidence pointers to exact publication snapshots

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_pointers",
        sa.Column("publication_snapshot_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "evidence_pointers",
        sa.Column("index_job_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "evidence_pointers",
        sa.Column("domain_release_id", sa.String(length=26), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_pointers_publication_snapshot",
        "evidence_pointers",
        "publication_snapshots",
        ["publication_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidence_pointers_index_job",
        "evidence_pointers",
        "jobs",
        ["index_job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidence_pointers_domain_release",
        "evidence_pointers",
        "domain_releases",
        ["domain_release_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_evidence_pointers_publication_pin",
        "evidence_pointers",
        "(publication_snapshot_id IS NULL AND index_job_id IS NULL "
        "AND domain_release_id IS NULL) OR "
        "(publication_snapshot_id IS NOT NULL AND index_job_id IS NOT NULL "
        "AND domain_release_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_evidence_pointers_publication_pin", "evidence_pointers", type_="check"
    )
    op.drop_constraint(
        "fk_evidence_pointers_domain_release", "evidence_pointers", type_="foreignkey"
    )
    op.drop_constraint("fk_evidence_pointers_index_job", "evidence_pointers", type_="foreignkey")
    op.drop_constraint(
        "fk_evidence_pointers_publication_snapshot",
        "evidence_pointers",
        type_="foreignkey",
    )
    op.drop_column("evidence_pointers", "domain_release_id")
    op.drop_column("evidence_pointers", "index_job_id")
    op.drop_column("evidence_pointers", "publication_snapshot_id")
