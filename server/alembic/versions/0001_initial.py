"""initial tables

Revision ID: 0001
Revises:
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORG_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"

def _ts_column(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


TIMESTAMP_COLS = [_ts_column("created_at"), _ts_column("updated_at")]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *TIMESTAMP_COLS,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "organization_id", sa.String(26), sa.ForeignKey("organizations.id"), nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_teacher", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *TIMESTAMP_COLS,
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_ip", sa.String(64)),
        sa.Column("user_agent", sa.String(255)),
        *TIMESTAMP_COLS,
    )
    op.create_index("ix_auth_sessions_user_active", "auth_sessions", ["user_id", "expires_at"])
    op.create_table(
        "courses",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "organization_id", sa.String(26), sa.ForeignKey("organizations.id"), nullable=False,
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("term", sa.String(50), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *TIMESTAMP_COLS,
    )
    op.create_table(
        "course_members",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *TIMESTAMP_COLS,
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_members_course_user"),
        sa.CheckConstraint(
            "role IN ('teacher','student','assistant')", name="ck_course_members_role"
        ),
        sa.CheckConstraint("status IN ('active','removed')", name="ck_course_members_status"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("actor_id", sa.String(26), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(26)),
        sa.Column("course_id", sa.String(26)),
        sa.Column("detail", sa.JSON),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        *TIMESTAMP_COLS,
        sa.UniqueConstraint(
            "idempotency_key", "user_id", "endpoint", name="uq_idempotency_key_user_endpoint"
        ),
    )
    op.execute(
        "INSERT INTO organizations (id, name, status) VALUES "
        f"('{DEFAULT_ORG_ID}', '默认学校组织', 'active') ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("audit_logs")
    op.drop_table("course_members")
    op.drop_table("courses")
    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_table("organizations")
