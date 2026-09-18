"""chat sessions, turns and learning state machine

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("chapter_object_id", sa.String(26)),
        sa.Column("question_version_id", sa.String(26)),
        sa.Column("title", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "mode IN ('course_qa','tutor','question_coach','review')",
            name="ck_chat_sessions_mode",
        ),
        sa.CheckConstraint(
            "status IN ('active','closed')", name="ck_chat_sessions_status"
        ),
    )
    op.create_index(
        "ix_chat_sessions_course_id", "chat_sessions", ["course_id"]
    )
    op.create_table(
        "chat_turns",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "session_id", sa.String(26), sa.ForeignKey("chat_sessions.id"), nullable=False
        ),
        sa.Column("client_turn_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON),
        sa.Column("verification", sa.JSON),
        sa.Column("refusal", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("finish_reason", sa.String(30)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("session_id", "client_turn_id", name="uq_chat_turns_client_id"),
        sa.CheckConstraint("role IN ('student','tutor')", name="ck_chat_turns_role"),
    )
    op.create_index(
        "ix_chat_turns_session_id", "chat_turns", ["session_id"]
    )
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("material_version_id", sa.String(26), nullable=False),
        sa.Column("chapter_object_id", sa.String(26)),
        sa.Column("state", sa.String(30), nullable=False, server_default="diagnose"),
        sa.Column("hint_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tutor_message", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('diagnose','teach','check','hint','practice','summary','completed')",
            name="ck_learning_sessions_state",
        ),
        sa.CheckConstraint(
            "status IN ('active','paused','closed')",
            name="ck_learning_sessions_status",
        ),
    )
    op.create_index(
        "ix_learning_sessions_course_id", "learning_sessions", ["course_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_sessions_course_id", table_name="learning_sessions"
    )
    op.drop_table("learning_sessions")
    op.drop_index("ix_chat_turns_session_id", table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_index("ix_chat_sessions_course", table_name="chat_sessions")
    op.drop_table("chat_sessions")
