"""add teacher intervention lifecycle

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interventions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(26),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "class_id",
            sa.String(26),
            sa.ForeignKey("course_classes.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.JSON()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "activity_type IN ('reteach','practice_set','mini_lab','discussion','review')",
            name="ck_interventions_activity_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','scheduled','active','completed','evaluated','archived')",
            name="ck_interventions_status",
        ),
    )
    op.create_index(
        "ix_interventions_course_status",
        "interventions",
        ["course_id", "status", "created_at"],
    )
    op.create_index(
        "ix_interventions_class_status",
        "interventions",
        ["class_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_interventions_class_status", table_name="interventions")
    op.drop_index("ix_interventions_course_status", table_name="interventions")
    op.drop_table("interventions")
