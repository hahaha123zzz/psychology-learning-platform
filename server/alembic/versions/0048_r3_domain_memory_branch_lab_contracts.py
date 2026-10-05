"""add R3 domain, memory provenance, branch receipt and lab invalidation contracts

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "domain_releases",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("course_id", sa.String(length=26), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("pack_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(length=26), nullable=False),
        sa.Column("reviewed_by", sa.String(length=26), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("published_by", sa.String(length=26), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.String(length=26), nullable=True),
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
        sa.CheckConstraint("version_no >= 1", name="ck_domain_releases_version"),
        sa.CheckConstraint(
            "status IN ('draft','ready','published','deprecated')",
            name="ck_domain_releases_status",
        ),
        sa.CheckConstraint("length(pack_sha256) = 64", name="ck_domain_releases_sha256"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["supersedes_id"], ["domain_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "version_no", name="uq_domain_releases_course_version"),
    )
    op.create_index(
        "ix_domain_releases_course_status",
        "domain_releases",
        ["course_id", "status", "version_no"],
    )

    op.create_table(
        "domain_review_decisions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("domain_release_id", sa.String(length=26), nullable=False),
        sa.Column("object_type", sa.String(length=30), nullable=False),
        sa.Column("object_key", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("reviewer_id", sa.String(length=26), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "object_type IN ('knowledge_point','relation','experiment','misconception')",
            name="ck_domain_review_object_type",
        ),
        sa.CheckConstraint(
            "decision IN ('approved','rejected','changes_requested')",
            name="ck_domain_review_decision",
        ),
        sa.ForeignKeyConstraint(["domain_release_id"], ["domain_releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_domain_review_decisions_release_object",
        "domain_review_decisions",
        ["domain_release_id", "object_type", "object_key", "created_at"],
    )

    op.add_column(
        "course_releases", sa.Column("domain_release_id", sa.String(length=26), nullable=True)
    )
    op.create_foreign_key(
        "fk_course_releases_domain_release",
        "course_releases",
        "domain_releases",
        ["domain_release_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "publication_snapshots", sa.Column("domain_release_id", sa.String(length=26), nullable=True)
    )
    op.create_foreign_key(
        "fk_publication_snapshots_domain_release",
        "publication_snapshots",
        "domain_releases",
        ["domain_release_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "retrieval_units", sa.Column("domain_release_id", sa.String(length=26), nullable=True)
    )
    op.create_foreign_key(
        "fk_retrieval_units_domain_release",
        "retrieval_units",
        "domain_releases",
        ["domain_release_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_retrieval_units_domain_release", "retrieval_units", ["domain_release_id"])

    op.add_column(
        "memory_items",
        sa.Column(
            "provenance_level", sa.String(length=30), server_default="inferred", nullable=False
        ),
    )
    op.add_column(
        "memory_items",
        sa.Column("evidence_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "memory_items", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memory_items", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memory_items", sa.Column("review_after", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memory_items", sa.Column("conflict_group_id", sa.String(length=26), nullable=True)
    )
    op.add_column(
        "memory_items",
        sa.Column("conflict_status", sa.String(length=20), server_default="none", nullable=False),
    )
    op.add_column("memory_items", sa.Column("conflict_resolution_reason", sa.Text(), nullable=True))
    op.add_column(
        "memory_items", sa.Column("conflict_resolved_by_id", sa.String(length=26), nullable=True)
    )
    op.add_column(
        "memory_items", sa.Column("conflict_resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE memory_items SET provenance_level = CASE source_type "
        "WHEN 'user' THEN 'explicit' WHEN 'quiz' THEN 'observed' "
        "WHEN 'practice' THEN 'observed' WHEN 'review' THEN 'observed' "
        "ELSE 'inferred' END"
    )
    op.create_foreign_key(
        "fk_memory_items_conflict_resolved_by",
        "memory_items",
        "users",
        ["conflict_resolved_by_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_memory_items_provenance_level",
        "memory_items",
        "provenance_level IN ('observed','inferred','explicit','teacher_confirmed')",
    )
    op.create_check_constraint(
        "ck_memory_items_conflict_status",
        "memory_items",
        "conflict_status IN ('none','open','resolved')",
    )
    op.create_index("ix_memory_items_expiry", "memory_items", ["user_id", "expires_at"])
    op.create_index(
        "ix_memory_items_conflict_group", "memory_items", ["user_id", "conflict_group_id"]
    )

    op.add_column(
        "chat_sessions", sa.Column("branch_merge_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "chat_sessions", sa.Column("branch_merge_payload_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "chat_sessions",
        sa.Column("branch_merge_result_turn_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "chat_sessions", sa.Column("branch_merged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_chat_sessions_branch_merge_result_turn",
        "chat_sessions",
        "chat_turns",
        ["branch_merge_result_turn_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_chat_sessions_branch_merge_receipt",
        "chat_sessions",
        "(branch_merge_key IS NULL AND branch_merge_payload_hash IS NULL "
        "AND branch_merge_result_turn_id IS NULL AND branch_merged_at IS NULL) OR "
        "(is_branch = true AND branch_merge_key IS NOT NULL "
        "AND branch_merge_payload_hash IS NOT NULL "
        "AND branch_merge_result_turn_id IS NOT NULL AND branch_merged_at IS NOT NULL)",
    )

    op.add_column(
        "mini_lab_sessions", sa.Column("invalidation_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "mini_lab_sessions",
        sa.Column("invalidation_payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "mini_lab_sessions",
        sa.Column("invalidated_by_user_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "mini_lab_sessions", sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "mini_lab_sessions", sa.Column("invalidation_reason", sa.String(length=500), nullable=True)
    )
    op.create_foreign_key(
        "fk_mini_lab_sessions_invalidated_by",
        "mini_lab_sessions",
        "users",
        ["invalidated_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    retained_domain_data = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM domain_releases) "
            "OR EXISTS (SELECT 1 FROM course_releases WHERE domain_release_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM publication_snapshots WHERE domain_release_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM retrieval_units WHERE domain_release_id IS NOT NULL)"
        )
    ).scalar_one()
    retained_r3_state = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM memory_items "
            "WHERE provenance_level = 'teacher_confirmed' "
            "OR evidence_refs <> '[]'::json OR valid_from IS NOT NULL OR expires_at IS NOT NULL "
            "OR review_after IS NOT NULL OR conflict_group_id IS NOT NULL "
            "OR conflict_status <> 'none' OR conflict_resolution_reason IS NOT NULL "
            "OR conflict_resolved_by_id IS NOT NULL OR conflict_resolved_at IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM chat_sessions WHERE branch_merge_key IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM mini_lab_sessions WHERE invalidation_key IS NOT NULL)"
        )
    ).scalar_one()
    if retained_domain_data or retained_r3_state:
        raise RuntimeError("Cannot downgrade 0048 while R3 domain or workflow data is retained")

    op.drop_constraint(
        "fk_mini_lab_sessions_invalidated_by", "mini_lab_sessions", type_="foreignkey"
    )
    op.drop_column("mini_lab_sessions", "invalidation_reason")
    op.drop_column("mini_lab_sessions", "invalidated_at")
    op.drop_column("mini_lab_sessions", "invalidated_by_user_id")
    op.drop_column("mini_lab_sessions", "invalidation_payload_hash")
    op.drop_column("mini_lab_sessions", "invalidation_key")

    op.drop_constraint("ck_chat_sessions_branch_merge_receipt", "chat_sessions", type_="check")
    op.drop_constraint(
        "fk_chat_sessions_branch_merge_result_turn", "chat_sessions", type_="foreignkey"
    )
    op.drop_column("chat_sessions", "branch_merged_at")
    op.drop_column("chat_sessions", "branch_merge_result_turn_id")
    op.drop_column("chat_sessions", "branch_merge_payload_hash")
    op.drop_column("chat_sessions", "branch_merge_key")

    op.drop_index("ix_memory_items_conflict_group", table_name="memory_items")
    op.drop_index("ix_memory_items_expiry", table_name="memory_items")
    op.drop_constraint("ck_memory_items_conflict_status", "memory_items", type_="check")
    op.drop_constraint("ck_memory_items_provenance_level", "memory_items", type_="check")
    op.drop_constraint("fk_memory_items_conflict_resolved_by", "memory_items", type_="foreignkey")
    for column in (
        "conflict_resolved_at",
        "conflict_resolved_by_id",
        "conflict_resolution_reason",
        "conflict_status",
        "conflict_group_id",
        "review_after",
        "expires_at",
        "valid_from",
        "evidence_refs",
        "provenance_level",
    ):
        op.drop_column("memory_items", column)

    op.drop_index("ix_retrieval_units_domain_release", table_name="retrieval_units")
    op.drop_constraint("fk_retrieval_units_domain_release", "retrieval_units", type_="foreignkey")
    op.drop_column("retrieval_units", "domain_release_id")
    op.drop_constraint(
        "fk_publication_snapshots_domain_release", "publication_snapshots", type_="foreignkey"
    )
    op.drop_column("publication_snapshots", "domain_release_id")
    op.drop_constraint("fk_course_releases_domain_release", "course_releases", type_="foreignkey")
    op.drop_column("course_releases", "domain_release_id")

    op.drop_index("ix_domain_review_decisions_release_object", table_name="domain_review_decisions")
    op.drop_table("domain_review_decisions")
    op.drop_index("ix_domain_releases_course_status", table_name="domain_releases")
    op.drop_table("domain_releases")
