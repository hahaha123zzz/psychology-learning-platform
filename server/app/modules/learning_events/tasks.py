from app.core.celery_app import celery_app
from app.core.task_loop import run_task
from app.db.session import session_factory
from app.modules.learning_events.qualification import qualify_pending_events


async def _qualify_pending_events(limit: int) -> dict[str, int]:
    async with session_factory() as db:
        return await qualify_pending_events(db, limit=limit)


@celery_app.task(name="learning_events.qualify_pending")
def qualify_pending(limit: int = 100) -> dict[str, int]:
    return run_task(_qualify_pending_events(limit))
