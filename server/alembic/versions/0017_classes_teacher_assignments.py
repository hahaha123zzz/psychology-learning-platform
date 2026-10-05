"""add course classes and explicit teacher assignments

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_classes",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(26),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("course_id", "code", name="uq_course_classes_course_code"),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_course_classes_status"),
    )
    op.create_index("ix_course_classes_course_status", "course_classes", ["course_id", "status"])
    op.create_table(
        "teacher_assignments",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "class_id",
            sa.String(26),
            sa.ForeignKey("course_classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teacher_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assignment_role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("assigned_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "class_id", "teacher_id", name="uq_teacher_assignments_class_teacher"
        ),
        sa.CheckConstraint(
            "assignment_role IN ('lead','assistant')", name="ck_teacher_assignments_role"
        ),
        sa.CheckConstraint("status IN ('active','ended')", name="ck_teacher_assignments_status"),
    )
    op.create_index(
        "ix_teacher_assignments_teacher_status",
        "teacher_assignments",
        ["teacher_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_assignments_teacher_status", table_name="teacher_assignments")
    op.drop_table("teacher_assignments")
    op.drop_index("ix_course_classes_course_status", table_name="course_classes")
    op.drop_table("course_classes")
