"""add shared R3 activity, rubric and release-assignment contracts

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "course_release_assignments",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("class_id", sa.String(26), nullable=False),
        sa.Column("course_release_id", sa.String(26), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("assigned_by", sa.String(26), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("supersedes_id", sa.String(26), nullable=True),
        sa.Column("closed_by", sa.String(26), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active','closed','revoked')", name="ck_course_release_assignments_status"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["course_classes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_release_id"], ["course_releases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["course_release_assignments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supersedes_id", name="uq_course_release_assignments_supersedes"),
    )
    op.create_index(
        "uq_course_release_assignments_active_class",
        "course_release_assignments",
        ["class_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_course_release_assignments_course",
        "course_release_assignments",
        ["course_id", "class_id", "assigned_at"],
    )

    op.create_table(
        "rubric_versions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("question_version_id", sa.String(26), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("approved_by", sa.String(26), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version_no >= 1", name="ck_rubric_versions_version"),
        sa.CheckConstraint("max_score > 0", name="ck_rubric_versions_max_score"),
        sa.CheckConstraint(
            "status IN ('draft','approved','retired')", name="ck_rubric_versions_status"
        ),
        sa.ForeignKeyConstraint(
            ["question_version_id"], ["question_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_version_id", "version_no", name="uq_rubric_versions_no"),
    )
    op.create_index(
        "ix_rubric_versions_question_status", "rubric_versions", ["question_version_id", "status"]
    )

    op.create_table(
        "question_purpose_approvals",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("question_version_id", sa.String(26), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reviewer_id", sa.String(26), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("purpose IN ('practice','formal')", name="ck_question_purpose_approval"),
        sa.CheckConstraint(
            "decision IN ('approved','revoked')", name="ck_question_purpose_decision"
        ),
        sa.ForeignKeyConstraint(
            ["question_version_id"], ["question_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_question_purpose_approvals_latest",
        "question_purpose_approvals",
        ["question_version_id", "purpose", "created_at"],
    )

    op.create_table(
        "teaching_activity_versions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("activity_key", sa.String(100), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("published_by", sa.String(26), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.String(26), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version_no >= 1", name="ck_teaching_activity_version_no"),
        sa.CheckConstraint(
            "status IN ('draft','ready','published','deprecated')",
            name="ck_teaching_activity_status",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["teaching_activity_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id", "activity_key", "version_no", name="uq_teaching_activity_version"
        ),
    )
    op.create_index(
        "ix_teaching_activity_course_status",
        "teaching_activity_versions",
        ["course_id", "status", "activity_key"],
    )

    op.create_table(
        "teaching_activity_runs",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("activity_version_id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("class_id", sa.String(26), nullable=False),
        sa.Column("course_release_assignment_id", sa.String(26), nullable=True),
        sa.Column("course_release_id", sa.String(26), nullable=True),
        sa.Column("target_snapshot", sa.JSON(), nullable=False),
        sa.Column("run_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), server_default="planned", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_sha256", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('planned','ready','active','paused','completed','cancelled')",
            name="ck_teaching_activity_runs_status",
        ),
        sa.CheckConstraint(
            "(idempotency_key IS NULL AND request_sha256 IS NULL) OR "
            "(idempotency_key IS NOT NULL AND request_sha256 IS NOT NULL)",
            name="ck_teaching_activity_runs_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["activity_version_id"], ["teaching_activity_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["course_classes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["course_release_assignment_id"], ["course_release_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["course_release_id"], ["course_releases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teaching_activity_runs_class_status",
        "teaching_activity_runs",
        ["class_id", "status", "created_at"],
    )
    op.create_index(
        "uq_teaching_activity_runs_idempotency",
        "teaching_activity_runs",
        ["course_id", "created_by", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "teacher_timeline_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("class_id", sa.String(26), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.String(26), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.String(26), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("phase IN ('planned','actual')", name="ck_teacher_timeline_phase"),
        sa.CheckConstraint(
            "subject_type IN ('activity','activity_run','intervention','annotation')",
            name="ck_teacher_timeline_subject",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["course_classes.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type", "source_id", "event_type", name="uq_teacher_timeline_source"
        ),
    )
    op.create_index(
        "ix_teacher_timeline_class_time",
        "teacher_timeline_events",
        ["class_id", "occurred_at", "id"],
    )

    op.create_table(
        "teacher_annotations",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("class_id", sa.String(26), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(26), nullable=False),
        sa.Column("visibility", sa.String(20), server_default="teacher_only", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("annotation", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(26), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('activity','evidence','knowledge_point','intervention')",
            name="ck_teacher_annotations_target",
        ),
        sa.CheckConstraint(
            "visibility IN ('teacher_only','student_visible')",
            name="ck_teacher_annotations_visibility",
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_teacher_annotations_status"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["course_classes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_annotations_class_target",
        "teacher_annotations",
        ["class_id", "target_type", "target_id"],
    )

    op.add_column("assessments", sa.Column("purpose", sa.String(20), nullable=True))
    op.add_column(
        "assessments", sa.Column("result_visibility_policy", sa.String(40), nullable=True)
    )
    op.add_column(
        "assessments", sa.Column("results_released_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "assessments", sa.Column("course_release_assignment_id", sa.String(26), nullable=True)
    )
    op.create_foreign_key(
        "fk_assessments_course_release_assignment",
        "assessments",
        "course_release_assignments",
        ["course_release_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_assessments_purpose",
        "assessments",
        "purpose IS NULL OR purpose IN ('practice','formal')",
    )
    op.create_check_constraint(
        "ck_assessments_result_visibility",
        "assessments",
        "result_visibility_policy IS NULL OR result_visibility_policy IN "
        "('immediate_after_submission','after_close','after_grading','manual_release')",
    )
    op.create_check_constraint(
        "ck_assessments_formal_visibility",
        "assessments",
        "purpose IS DISTINCT FROM 'formal' OR result_visibility_policy IS DISTINCT FROM "
        "'immediate_after_submission'",
    )
    op.create_index(
        "ix_assessments_release_assignment", "assessments", ["course_release_assignment_id"]
    )
    op.add_column("assessment_items", sa.Column("rubric_version_id", sa.String(26), nullable=True))
    op.create_foreign_key(
        "fk_assessment_items_rubric_version",
        "assessment_items",
        "rubric_versions",
        ["rubric_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    connection = op.get_bind()
    retained = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM course_release_assignments) "
            "OR EXISTS (SELECT 1 FROM rubric_versions) "
            "OR EXISTS (SELECT 1 FROM question_purpose_approvals) "
            "OR EXISTS (SELECT 1 FROM teaching_activity_versions) "
            "OR EXISTS (SELECT 1 FROM teaching_activity_runs) "
            "OR EXISTS (SELECT 1 FROM teacher_timeline_events) "
            "OR EXISTS (SELECT 1 FROM teacher_annotations) "
            "OR EXISTS (SELECT 1 FROM assessments WHERE purpose IS NOT NULL "
            "OR result_visibility_policy IS NOT NULL OR results_released_at IS NOT NULL "
            "OR course_release_assignment_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM assessment_items WHERE rubric_version_id IS NOT NULL)"
        )
    ).scalar_one()
    if retained:
        raise RuntimeError("Cannot downgrade 0049 while R3 teaching or assessment data is retained")

    op.drop_constraint("fk_assessment_items_rubric_version", "assessment_items", type_="foreignkey")
    op.drop_column("assessment_items", "rubric_version_id")
    op.drop_index("ix_assessments_release_assignment", table_name="assessments")
    op.drop_constraint("ck_assessments_formal_visibility", "assessments", type_="check")
    op.drop_constraint("ck_assessments_result_visibility", "assessments", type_="check")
    op.drop_constraint("ck_assessments_purpose", "assessments", type_="check")
    op.drop_constraint(
        "fk_assessments_course_release_assignment", "assessments", type_="foreignkey"
    )
    op.drop_column("assessments", "course_release_assignment_id")
    op.drop_column("assessments", "results_released_at")
    op.drop_column("assessments", "result_visibility_policy")
    op.drop_column("assessments", "purpose")

    op.drop_index("ix_teacher_annotations_class_target", table_name="teacher_annotations")
    op.drop_table("teacher_annotations")
    op.drop_index("ix_teacher_timeline_class_time", table_name="teacher_timeline_events")
    op.drop_table("teacher_timeline_events")
    op.drop_index("uq_teaching_activity_runs_idempotency", table_name="teaching_activity_runs")
    op.drop_index("ix_teaching_activity_runs_class_status", table_name="teaching_activity_runs")
    op.drop_table("teaching_activity_runs")
    op.drop_index("ix_teaching_activity_course_status", table_name="teaching_activity_versions")
    op.drop_table("teaching_activity_versions")
    op.drop_index("ix_question_purpose_approvals_latest", table_name="question_purpose_approvals")
    op.drop_table("question_purpose_approvals")
    op.drop_index("ix_rubric_versions_question_status", table_name="rubric_versions")
    op.drop_table("rubric_versions")
    op.drop_index("ix_course_release_assignments_course", table_name="course_release_assignments")
    op.drop_index(
        "uq_course_release_assignments_active_class", table_name="course_release_assignments"
    )
    op.drop_table("course_release_assignments")
