"""Add immutable teacher grading decisions and released score records.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_grading_decisions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("attempt_id", sa.String(length=26), nullable=False),
        sa.Column("question_version_id", sa.String(length=26), nullable=False),
        sa.Column("grader_id", sa.String(length=26), nullable=False),
        sa.Column("decision_version", sa.Integer(), nullable=False),
        sa.Column("points_awarded", sa.Float(), nullable=False),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_id", sa.String(length=26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_version >= 1 AND points_awarded >= 0 AND points_awarded <= max_points",
            name="ck_teacher_grading_decisions_score_range",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["grader_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"]),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["teacher_grading_decisions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            "question_version_id",
            "decision_version",
            name="uq_teacher_grading_decisions_version",
        ),
    )
    op.create_index(
        "ix_teacher_grading_decisions_attempt",
        "teacher_grading_decisions",
        ["attempt_id", "question_version_id"],
    )
    op.create_table(
        "score_records",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("attempt_id", sa.String(length=26), nullable=False),
        sa.Column("score_version", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=26), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_id", sa.String(length=26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score_version >= 1 AND score >= 0 AND score <= max_score",
            name="ck_score_records_score_range",
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["supersedes_id"], ["score_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id", "score_version", name="uq_score_records_attempt_version"
        ),
    )
    op.create_index(
        "ix_score_records_attempt_version",
        "score_records",
        ["attempt_id", "score_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_score_records_attempt_version", table_name="score_records")
    op.drop_table("score_records")
    op.drop_index(
        "ix_teacher_grading_decisions_attempt", table_name="teacher_grading_decisions"
    )
    op.drop_table("teacher_grading_decisions")
