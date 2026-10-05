"""bind learning runs and evidence to course release assignments

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table_name in ("learning_sessions", "attempts", "learning_evidences"):
        op.add_column(
            table_name,
            sa.Column("course_release_assignment_id", sa.String(26), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("course_release_id", sa.String(26), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_course_release_assignment",
            table_name,
            "course_release_assignments",
            ["course_release_assignment_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            f"fk_{table_name}_course_release",
            table_name,
            "course_releases",
            ["course_release_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            f"ck_{table_name}_release_pair",
            table_name,
            "(course_release_assignment_id IS NULL) = (course_release_id IS NULL)",
        )
        op.create_index(
            f"ix_{table_name}_release_assignment",
            table_name,
            ["course_release_assignment_id"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    retained = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM learning_sessions "
            "WHERE course_release_assignment_id IS NOT NULL OR course_release_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM attempts "
            "WHERE course_release_assignment_id IS NOT NULL OR course_release_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM learning_evidences "
            "WHERE course_release_assignment_id IS NOT NULL OR course_release_id IS NOT NULL)"
        )
    ).scalar_one()
    if retained:
        raise RuntimeError("Cannot downgrade 0050 while release-bound learning data is retained")

    for table_name in ("learning_evidences", "attempts", "learning_sessions"):
        op.drop_index(f"ix_{table_name}_release_assignment", table_name=table_name)
        op.drop_constraint(f"ck_{table_name}_release_pair", table_name, type_="check")
        op.drop_constraint(
            f"fk_{table_name}_course_release", table_name, type_="foreignkey"
        )
        op.drop_constraint(
            f"fk_{table_name}_course_release_assignment", table_name, type_="foreignkey"
        )
        op.drop_column(table_name, "course_release_id")
        op.drop_column(table_name, "course_release_assignment_id")
