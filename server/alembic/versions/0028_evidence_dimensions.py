"""add evidence dimensions and independence metadata

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learning_evidences",
        sa.Column("dimension", sa.String(20), nullable=False, server_default="understand"),
    )
    op.add_column(
        "learning_evidences",
        sa.Column(
            "independence_status", sa.String(20), nullable=False, server_default="unknown"
        ),
    )
    op.add_column("learning_evidences", sa.Column("context_key", sa.String(100)))
    op.add_column(
        "learning_evidences",
        sa.Column("quality_status", sa.String(20), nullable=False, server_default="valid"),
    )
    op.add_column("learning_evidences", sa.Column("invalidated_reason", sa.String(500)))
    op.create_check_constraint(
        "ck_learning_evidences_dimension",
        "learning_evidences",
        "dimension IN ('recall','understand','discriminate','apply','transfer','retention')",
    )
    op.create_check_constraint(
        "ck_learning_evidences_independence",
        "learning_evidences",
        "independence_status IN ('independent','supported','unknown')",
    )
    op.create_check_constraint(
        "ck_learning_evidences_quality",
        "learning_evidences",
        "quality_status IN ('valid','invalidated')",
    )
    op.add_column(
        "mastery_states",
        sa.Column("context_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "mastery_states",
        sa.Column(
            "independent_evidence_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("mastery_states", "independent_evidence_count")
    op.drop_column("mastery_states", "context_count")
    op.drop_constraint("ck_learning_evidences_quality", "learning_evidences", type_="check")
    op.drop_constraint(
        "ck_learning_evidences_independence", "learning_evidences", type_="check"
    )
    op.drop_constraint("ck_learning_evidences_dimension", "learning_evidences", type_="check")
    op.drop_column("learning_evidences", "invalidated_reason")
    op.drop_column("learning_evidences", "quality_status")
    op.drop_column("learning_evidences", "context_key")
    op.drop_column("learning_evidences", "independence_status")
    op.drop_column("learning_evidences", "dimension")
