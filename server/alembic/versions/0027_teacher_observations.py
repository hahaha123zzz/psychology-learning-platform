"""add teacher observations

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_observations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(26),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teacher_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("observation_type", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("qualification_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("algorithm_version", sa.String(50)),
        sa.Column("reviewed_by", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column("review_reason", sa.String(500)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "observation_type IN ('misconception','strategy','support_need','progress')",
            name="ck_teacher_observations_type",
        ),
        sa.CheckConstraint(
            "qualification_status IN ('pending','qualified','rejected')",
            name="ck_teacher_observations_qualification",
        ),
    )
    op.create_index(
        "ix_teacher_observations_course_student",
        "teacher_observations",
        ["course_id", "student_id", "created_at"],
    )
    op.create_index(
        "ix_teacher_observations_course_status",
        "teacher_observations",
        ["course_id", "qualification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_observations_course_status", table_name="teacher_observations")
    op.drop_index("ix_teacher_observations_course_student", table_name="teacher_observations")
    op.drop_table("teacher_observations")
