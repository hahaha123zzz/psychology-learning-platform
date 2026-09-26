"""add resumable upload sessions and durable job metadata

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column(
        "jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("jobs", sa.Column("checkpoint", sa.JSON()))
    op.add_column(
        "jobs",
        sa.Column("worker_backend", sa.String(20), nullable=False, server_default="in_process"),
    )
    op.create_check_constraint(
        "ck_jobs_worker_backend", "jobs", "worker_backend IN ('in_process','celery')"
    )
    op.create_index("ix_jobs_heartbeat", "jobs", ["status", "last_heartbeat_at"])
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("course_id", sa.String(26), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("material_type", sa.String(30), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("part_size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("multipart_upload_id", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("sha256", sa.String(64)),
        sa.Column("material_id", sa.String(26), sa.ForeignKey("materials.id")),
        sa.Column("material_version_id", sa.String(26), sa.ForeignKey("material_versions.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('created','uploading','uploaded','verifying',"
            "'completed','failed','cancelled','expired')",
            name="ck_upload_sessions_status",
        ),
        sa.CheckConstraint(
            "material_type IN ('textbook','slides','handout','exercise','reference','other')",
            name="ck_upload_sessions_material_type",
        ),
    )
    op.create_index(
        "ix_upload_sessions_course_status",
        "upload_sessions",
        ["course_id", "status", "created_at"],
    )
    op.create_index(
        "ix_upload_sessions_creator_status", "upload_sessions", ["created_by", "status"]
    )
    op.create_table(
        "upload_parts",
        sa.Column(
            "upload_session_id",
            sa.String(26),
            sa.ForeignKey("upload_sessions.id"),
            primary_key=True,
        ),
        sa.Column("part_number", sa.Integer(), primary_key=True),
        sa.Column("etag", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("part_number >= 1", name="ck_upload_parts_number"),
        sa.CheckConstraint("size_bytes > 0", name="ck_upload_parts_size"),
    )


def downgrade() -> None:
    op.drop_table("upload_parts")
    op.drop_index("ix_upload_sessions_creator_status", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_course_status", table_name="upload_sessions")
    op.drop_table("upload_sessions")
    op.drop_index("ix_jobs_heartbeat", table_name="jobs")
    op.drop_constraint("ck_jobs_worker_backend", "jobs", type_="check")
    op.drop_column("jobs", "worker_backend")
    op.drop_column("jobs", "checkpoint")
    op.drop_column("jobs", "attempt_count")
    op.drop_column("jobs", "last_heartbeat_at")
