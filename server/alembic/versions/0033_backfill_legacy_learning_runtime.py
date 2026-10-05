"""Backfill runtime aggregates for learning sessions created before 0032.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-03
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.base import new_ulid

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT ls.id, ls.user_id, ls.course_id, ls.material_version_id,
                   ls.chapter_object_id, ls.state, ls.hint_level, ls.status,
                   ls.version, ls.created_at
            FROM learning_sessions AS ls
            LEFT JOIN current_learning_tasks AS task
              ON task.legacy_session_id = ls.id
            WHERE task.id IS NULL
            ORDER BY ls.created_at, ls.id
            """
        )
    )

    while batch := rows.fetchmany(500):
        for row in batch:
            task_status = "completed" if row.state == "completed" else row.status
            teaching_status = "closed" if row.state == "completed" else row.status
            episode_status = "completed" if row.state == "completed" else row.status
            connection.execute(
                sa.text(
                    """
                    INSERT INTO current_learning_tasks (
                        id, user_id, course_id, legacy_session_id, material_version_id,
                        chapter_object_id, goal, release_snapshot, completion, status,
                        version, created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :course_id, :legacy_session_id, :material_version_id,
                        :chapter_object_id, CAST(:goal AS JSON), NULL,
                        CAST(:completion AS JSON), :status, :version, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "course_id": row.course_id,
                    "legacy_session_id": row.id,
                    "material_version_id": row.material_version_id,
                    "chapter_object_id": row.chapter_object_id,
                    "goal": json.dumps(
                        {"type": "legacy_session", "source": "learning_sessions"}
                    ),
                    "completion": json.dumps(
                        {
                            "status": "completed" if row.state == "completed" else "in_progress",
                            "activity_completed": row.state == "completed",
                            "source": "legacy_state",
                        }
                    ),
                    "status": task_status,
                    "version": row.version,
                    "created_at": row.created_at,
                },
            )
            teaching_id = new_ulid()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO teaching_sessions (
                        id, task_id, state, status, state_version, context,
                        hint_budget, version, created_at, updated_at
                    ) VALUES (
                        :id, :task_id, :state, :status, :state_version,
                        CAST(:context AS JSON), :hint_budget, :version, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": teaching_id,
                    "task_id": row.id,
                    "state": row.state,
                    "status": teaching_status,
                    "state_version": row.version,
                    "context": json.dumps(
                        {
                            "course_id": row.course_id,
                            "material_version_id": row.material_version_id,
                            "chapter_object_id": row.chapter_object_id,
                            "source": "legacy_state",
                        }
                    ),
                    "hint_budget": max(0, 3 - row.hint_level),
                    "version": row.version,
                    "created_at": row.created_at,
                },
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO learning_episodes (
                        id, task_id, teaching_session_id, episode_no, status,
                        turn_count, summary, started_at, ended_at, created_at, updated_at
                    ) VALUES (
                        :id, :task_id, :teaching_session_id, 1, :status,
                        0, CAST(:summary AS JSON), :started_at, :ended_at, :started_at, :started_at
                    )
                    """
                ),
                {
                    "id": new_ulid(),
                    "task_id": row.id,
                    "teaching_session_id": teaching_id,
                    "status": episode_status,
                    "summary": json.dumps(
                        {"source": "legacy_state", "turn_count": "unknown"}
                    ),
                    "started_at": row.created_at,
                    "ended_at": row.created_at if row.state == "completed" else None,
                },
            )


def downgrade() -> None:
    # Backfilled aggregate rows are mixed with rows created by the live application.
    # Deleting rows by their inferred shape could remove user activity, so this
    # data migration is intentionally irreversible; repair forward if necessary.
    pass
