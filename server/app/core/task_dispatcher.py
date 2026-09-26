"""任务派发边界：开发/测试可进程内执行，默认由 Celery Worker 消费。"""

from app.core.config import get_settings


def dispatch_parse_job(job_id: str, version_id: str) -> None:
    if get_settings().task_backend == "in_process":
        from app.modules.materials.service import spawn_parse_job

        spawn_parse_job(job_id, version_id)
        return
    from app.core.celery_app import celery_app

    celery_app.send_task("materials.parse", args=[job_id, version_id])


def dispatch_embed_job(job_id: str, version_id: str) -> None:
    if get_settings().task_backend == "in_process":
        from app.modules.knowledge.service import spawn_embed_job

        spawn_embed_job(job_id, version_id)
        return
    from app.core.celery_app import celery_app

    celery_app.send_task("knowledge.embed", args=[job_id, version_id])
