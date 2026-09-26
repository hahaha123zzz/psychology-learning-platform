from app.core.celery_app import celery_app
from app.core.task_loop import run_task
from app.modules.materials.service import run_parse_job


@celery_app.task(name="materials.parse")
def parse_material(job_id: str, version_id: str) -> None:
    run_task(run_parse_job(job_id, version_id))
