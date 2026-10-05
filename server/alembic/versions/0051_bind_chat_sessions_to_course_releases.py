"""bind tutor chat sessions to course release assignments

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("course_release_assignment_id", sa.String(26), nullable=True),
    )
    op.add_column("chat_sessions", sa.Column("course_release_id", sa.String(26), nullable=True))
    op.create_foreign_key(
        "fk_chat_sessions_course_release_assignment",
        "chat_sessions",
        "course_release_assignments",
        ["course_release_assignment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_chat_sessions_course_release",
        "chat_sessions",
        "course_releases",
        ["course_release_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_chat_sessions_release_pair",
        "chat_sessions",
        "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
    )
    op.create_index(
        "ix_chat_sessions_release_assignment", "chat_sessions", ["course_release_assignment_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    retained = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM chat_sessions "
            "WHERE course_release_assignment_id IS NOT NULL OR course_release_id IS NOT NULL)"
        )
    ).scalar_one()
    if retained:
        raise RuntimeError("Cannot downgrade 0051 while release-bound Tutor sessions are retained")

    op.drop_index("ix_chat_sessions_release_assignment", table_name="chat_sessions")
    op.drop_constraint("ck_chat_sessions_release_pair", "chat_sessions", type_="check")
    op.drop_constraint("fk_chat_sessions_course_release", "chat_sessions", type_="foreignkey")
    op.drop_constraint(
        "fk_chat_sessions_course_release_assignment", "chat_sessions", type_="foreignkey"
    )
    op.drop_column("chat_sessions", "course_release_id")
    op.drop_column("chat_sessions", "course_release_assignment_id")
