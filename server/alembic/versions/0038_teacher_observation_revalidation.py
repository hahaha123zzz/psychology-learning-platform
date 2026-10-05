"""Add class scope and independent revalidation to teacher observations.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teacher_observations",
        sa.Column("class_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "teacher_observations",
        sa.Column(
            "review_decision",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "teacher_observations",
        sa.Column(
            "verification_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "teacher_observations",
        sa.Column("verification_event_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "teacher_observations",
        sa.Column("verification_qualification_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "teacher_observations",
        sa.Column(
            "verification_evidence_ids",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "teacher_observations",
        sa.Column("verification_algorithm_version", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "teacher_observations",
        sa.Column("verification_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "teacher_observations",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE teacher_observations "
            "SET review_decision = CASE "
            "WHEN reviewed_at IS NULL THEN 'pending' "
            "WHEN qualification_status = 'rejected' THEN 'rejected' "
            "ELSE 'accepted' END"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE teacher_observations "
            "SET qualification_status = 'pending' "
            "WHERE qualification_status = 'qualified'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE teacher_observations SET verification_status = 'rejected' "
            "WHERE review_decision = 'rejected'"
        )
    )
    bind.execute(
        sa.text(
            "WITH one_class AS ("
            " SELECT cm.user_id, cc.course_id, MIN(cm.class_id) AS class_id "
            " FROM class_members cm "
            " JOIN course_classes cc ON cc.id = cm.class_id "
            " WHERE cm.status = 'active' AND cc.status = 'active' "
            " GROUP BY cm.user_id, cc.course_id HAVING COUNT(*) = 1"
            ") UPDATE teacher_observations o SET class_id = one_class.class_id "
            "FROM one_class WHERE one_class.user_id = o.student_id "
            "AND one_class.course_id = o.course_id"
        )
    )

    op.create_foreign_key(
        "fk_teacher_observation_class",
        "teacher_observations",
        "course_classes",
        ["class_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_teacher_observation_event",
        "teacher_observations",
        "learning_events",
        ["verification_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_teacher_observation_qualification",
        "teacher_observations",
        "learning_qualifications",
        ["verification_qualification_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_teacher_observations_verification_event",
        "teacher_observations",
        ["verification_event_id"],
    )
    op.create_unique_constraint(
        "uq_teacher_observations_verification_qualification",
        "teacher_observations",
        ["verification_qualification_id"],
    )
    op.create_check_constraint(
        "ck_teacher_observations_review_decision",
        "teacher_observations",
        "review_decision IN ('pending','accepted','rejected')",
    )
    op.create_check_constraint(
        "ck_teacher_observations_verification_status",
        "teacher_observations",
        "verification_status IN ('pending','qualified','rejected','invalidated')",
    )
    op.create_index(
        "ix_teacher_observations_class_status",
        "teacher_observations",
        ["class_id", "qualification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_observations_class_status", table_name="teacher_observations")
    op.drop_constraint(
        "ck_teacher_observations_verification_status",
        "teacher_observations",
        type_="check",
    )
    op.drop_constraint(
        "ck_teacher_observations_review_decision",
        "teacher_observations",
        type_="check",
    )
    op.drop_constraint(
        "uq_teacher_observations_verification_qualification",
        "teacher_observations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_teacher_observations_verification_event",
        "teacher_observations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_teacher_observation_qualification",
        "teacher_observations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_teacher_observation_event",
        "teacher_observations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_teacher_observation_class",
        "teacher_observations",
        type_="foreignkey",
    )
    op.drop_column("teacher_observations", "verified_at")
    op.drop_column("teacher_observations", "verification_reason")
    op.drop_column("teacher_observations", "verification_algorithm_version")
    op.drop_column("teacher_observations", "verification_evidence_ids")
    op.drop_column("teacher_observations", "verification_qualification_id")
    op.drop_column("teacher_observations", "verification_event_id")
    op.drop_column("teacher_observations", "verification_status")
    op.drop_column("teacher_observations", "review_decision")
    op.drop_column("teacher_observations", "class_id")
