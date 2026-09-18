"""mastery, memory, model call logs

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_evidences",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("knowledge_point", sa.String(200), nullable=False),
        sa.Column("question_version_id", sa.String(26), nullable=False),
        sa.Column("attempt_id", sa.String(26)),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("hints_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct", sa.Boolean, nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_type IN ('formal_quiz','practice','review')",
            name="ck_learning_evidences_source",
        ),
    )
    op.create_index(
        "ix_learning_evidences_user_course", "learning_evidences", ["user_id", "course_id"]
    )
    op.create_table(
        "mastery_states",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26), nullable=False),
        sa.Column("knowledge_point", sa.String(200), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("evidence_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_ratio", sa.Float, nullable=False),
        sa.Column("weight_score", sa.Float, nullable=False),
        sa.Column("last_evidence_id", sa.String(26)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "course_id", "knowledge_point", name="uq_mastery_user_course_kp"
        ),
        sa.CheckConstraint(
            "state IN ('not_started','learning','needs_consolidation','proficient','mastered')",
            name="ck_mastery_state",
        ),
    )
    op.create_index(
        "ix_mastery_states_user_course", "mastery_states", ["user_id", "course_id"]
    )
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(26)),
        sa.Column("layer", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(64)),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("superseded_by_id", sa.String(26)),
        sa.Column("stale", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("layer IN ('L1','L2','L3')", name="ck_memory_items_layer"),
        sa.CheckConstraint(
            "source_type IN ('quiz','tutor','practice','user','review')",
            name="ck_memory_items_source",
        ),
    )
    op.create_index("ix_memory_items_user", "memory_items", ["user_id"])
    op.create_table(
        "model_call_logs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("user_id", sa.String(26)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('ok','timeout','error','budget_exceeded','circuit_open')",
            name="ck_model_call_logs_status",
        ),
    )
    op.create_index(
        "ix_model_call_logs_purpose", "model_call_logs", ["purpose"]
    )


def downgrade() -> None:
    op.drop_index("ix_model_call_logs_purpose", table_name="model_call_logs")
    op.drop_table("model_call_logs")
    op.drop_index("ix_memory_items_user", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index("ix_mastery_states_user_course", table_name="mastery_states")
    op.drop_table("mastery_states")
    op.drop_index(
        "ix_learning_evidences_user_course", table_name="learning_evidences"
    )
    op.drop_table("learning_evidences")
