from celery import Celery

from app.core.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "psychology_learning",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    app.conf.update(
        imports=(
            "app.modules.materials.tasks",
            "app.modules.knowledge.tasks",
            "app.modules.learning_events.tasks",
            "app.modules.memory.tasks",
            "app.modules.outbox_tasks",
        ),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery()
