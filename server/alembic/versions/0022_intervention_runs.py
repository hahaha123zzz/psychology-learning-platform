"""add per-student intervention runs

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intervention_runs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "intervention_id",
            sa.String(26),
            sa.ForeignKey("interventions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.String(26),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.JSON()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "intervention_id", "user_id", name="uq_intervention_runs_intervention_user"
        ),
        sa.CheckConstraint(
            "status IN ('scheduled','in_progress','paused','completed','cancelled')",
            name="ck_intervention_runs_status",
        ),
    )
    op.create_index(
        "ix_intervention_runs_intervention_status",
        "intervention_runs",
        ["intervention_id", "status"],
    )
    op.create_index(
        "ix_intervention_runs_user_status",
        "intervention_runs",
        ["user_id", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intervention_runs_user_status", table_name="intervention_runs")
    op.drop_index("ix_intervention_runs_intervention_status", table_name="intervention_runs")
    op.drop_table("intervention_runs")
