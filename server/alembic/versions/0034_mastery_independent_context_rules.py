"""Require independent evidence across contexts for mastery promotion.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mastery_states",
        sa.Column(
            "algorithm_version",
            sa.String(length=50),
            nullable=False,
            server_default="mastery-v1-legacy",
        ),
    )
    op.add_column(
        "mastery_states",
        sa.Column("state_reason", sa.String(length=500), nullable=False, server_default=""),
    )
    op.execute(
        sa.text(
            """
            UPDATE mastery_states
            SET state = CASE
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND independent_evidence_count >= 3 AND context_count >= 2
                     AND COALESCE((
                         SELECT evidence.correct
                         FROM learning_evidences AS evidence
                         WHERE evidence.id = mastery_states.last_evidence_id
                     ), true)
                    THEN 'mastered'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND independent_evidence_count < 3
                    THEN 'learning'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND context_count < 2
                    THEN 'learning'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND independent_evidence_count >= 2 AND context_count >= 2
                     AND COALESCE((
                         SELECT evidence.correct
                         FROM learning_evidences AS evidence
                         WHERE evidence.id = mastery_states.last_evidence_id
                     ), true)
                    THEN 'proficient'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND independent_evidence_count < 2
                    THEN 'learning'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND context_count < 2
                    THEN 'learning'
                WHEN evidence_count >= 2 AND correct_ratio >= 0.4
                    THEN 'needs_consolidation'
                WHEN evidence_count >= 1
                    THEN 'learning'
                ELSE 'not_started'
            END,
            algorithm_version = 'mastery-v2-independent-context',
            state_reason = CASE
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND independent_evidence_count < 3
                    THEN '升级后需至少3条独立证据方可标记已掌握。'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND context_count < 2
                    THEN '升级后需至少覆盖2种情境方可标记已掌握。'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND NOT COALESCE((
                         SELECT evidence.correct
                         FROM learning_evidences AS evidence
                         WHERE evidence.id = mastery_states.last_evidence_id
                     ), true)
                    THEN '最近一次验证未通过，需要巩固后再次检查。'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                    THEN '达到正确率与证据量门槛，且有3条独立证据覆盖至少2种情境。'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND independent_evidence_count < 2
                    THEN '升级后需至少2条独立证据方可标记基本掌握。'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND context_count < 2
                    THEN '升级后需至少覆盖2种情境方可标记基本掌握。'
                WHEN evidence_count >= 4 AND correct_ratio >= 0.85 AND weight_score >= 3.0
                     AND NOT COALESCE((
                         SELECT evidence.correct
                         FROM learning_evidences AS evidence
                         WHERE evidence.id = mastery_states.last_evidence_id
                     ), true)
                    THEN '最近一次验证未通过，需要巩固后再次检查。'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                     AND NOT COALESCE((
                         SELECT evidence.correct
                         FROM learning_evidences AS evidence
                         WHERE evidence.id = mastery_states.last_evidence_id
                     ), true)
                    THEN '最近一次验证未通过，需要巩固后再次检查。'
                WHEN evidence_count >= 3 AND correct_ratio >= 0.7 AND weight_score >= 1.5
                    THEN '达到熟练门槛，且有2条独立证据覆盖至少2种情境。'
                WHEN evidence_count >= 2 AND correct_ratio >= 0.4
                    THEN '已有多条证据，但当前表现仍需要巩固。'
                WHEN evidence_count = 0
                    THEN '尚无有效学习证据。'
                ELSE '证据尚不足以稳定判断掌握情况。'
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_column("mastery_states", "state_reason")
    op.drop_column("mastery_states", "algorithm_version")
