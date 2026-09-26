from app.core.celery_app import celery_app
from app.core.task_loop import run_task
from app.modules.knowledge.service import run_embed_job


@celery_app.task(name="knowledge.embed")
def embed_material(job_id: str, version_id: str) -> None:
    run_task(run_embed_job(job_id, version_id))
