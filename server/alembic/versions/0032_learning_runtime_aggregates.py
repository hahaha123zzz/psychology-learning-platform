"""add CurrentLearningTask, TeachingSession and LearningEpisode aggregates

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "current_learning_tasks",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("legacy_session_id", sa.String(length=26), nullable=False),
        sa.Column("material_version_id", sa.String(length=26), nullable=False),
        sa.Column("chapter_object_id", sa.String(length=26), nullable=True),
        sa.Column("goal", sa.JSON(), nullable=False),
        sa.Column("release_snapshot", sa.JSON(), nullable=True),
        sa.Column("completion", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','completed','closed')",
            name="ck_current_learning_tasks_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["legacy_session_id"], ["learning_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_session_id", name="uq_current_learning_tasks_legacy_session"),
    )
    op.create_index(
        "ix_current_learning_tasks_course_id", "current_learning_tasks", ["course_id"], unique=False
    )
    op.create_index(
        "ix_current_learning_tasks_user_course",
        "current_learning_tasks",
        ["user_id", "course_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "teaching_sessions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("task_id", sa.String(length=26), nullable=False),
        sa.Column("state", sa.String(length=30), server_default="diagnose", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("state_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("hint_budget", sa.Integer(), server_default="3", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','closed')", name="ck_teaching_sessions_status"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["current_learning_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_teaching_sessions_task"),
    )

    op.create_table(
        "learning_episodes",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("task_id", sa.String(length=26), nullable=False),
        sa.Column("teaching_session_id", sa.String(length=26), nullable=False),
        sa.Column("episode_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','completed','closed')", name="ck_learning_episodes_status"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["current_learning_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["teaching_session_id"], ["teaching_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "episode_no", name="uq_learning_episodes_task_no"),
    )


def downgrade() -> None:
    op.drop_table("learning_episodes")
    op.drop_table("teaching_sessions")
    op.drop_index("ix_current_learning_tasks_user_course", table_name="current_learning_tasks")
    op.drop_index("ix_current_learning_tasks_course_id", table_name="current_learning_tasks")
    op.drop_table("current_learning_tasks")
