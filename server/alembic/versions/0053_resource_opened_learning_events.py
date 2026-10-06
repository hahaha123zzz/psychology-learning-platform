"""allow non-evidence resource usage events

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint("ck_learning_events_type", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_type",
        "learning_events",
        "event_type IN ('task_viewed','answer_submitted','tutor_responded',"
        "'lab_trial_completed','feedback_submitted','RESOURCE_OPENED')",
    )
    op.drop_constraint("ck_learning_events_source", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_source",
        "learning_events",
        "source_type IN ('tutor','assessment','practice','review','lab','system','resource')",
    )


def downgrade() -> None:
    # Preserve non-evidence usage history. Refuse downgrade before changing
    # constraints while rows introduced by this revision still exist.
    has_resource_opened = op.get_bind().exec_driver_sql(
        "SELECT EXISTS (SELECT 1 FROM learning_events "
        "WHERE event_type = 'RESOURCE_OPENED')"
    ).scalar_one()
    if has_resource_opened:
        raise RuntimeError(
            "Cannot downgrade 0053 while RESOURCE_OPENED events exist; "
            "preserve the event history before retrying."
        )
    op.drop_constraint("ck_learning_events_source", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_source",
        "learning_events",
        "source_type IN ('tutor','assessment','practice','review','lab','system')",
    )
    op.drop_constraint("ck_learning_events_type", "learning_events", type_="check")
    op.create_check_constraint(
        "ck_learning_events_type",
        "learning_events",
        "event_type IN ('task_viewed','answer_submitted','tutor_responded',"
        "'lab_trial_completed','feedback_submitted')",
    )
