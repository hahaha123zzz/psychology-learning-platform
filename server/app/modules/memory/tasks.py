"""持久隐私删除工作单的 Celery 执行入口。"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.task_loop import run_task
from app.db.models import AuditLog, PrivacyDeletionRequest
from app.db.session import session_factory
from app.modules.memory.deletion import RETAINED_CATEGORIES, delete_personal_learning_data


def dispatch_privacy_deletion(request_id: str) -> None:
    """投递可安全重复的删除任务；数据库工作单保留投递失败后的恢复依据。"""
    celery_app.send_task("privacy.deletion.execute", args=[request_id])


async def _execute_privacy_deletion(request_id: str) -> dict[str, str | int]:
    try:
        async with session_factory() as db:
            async with db.begin():
                deletion = await db.scalar(
                    select(PrivacyDeletionRequest)
                    .where(PrivacyDeletionRequest.id == request_id)
                    .with_for_update()
                )
                if deletion is None:
                    return {"status": "not_found"}
                if deletion.status == "completed_with_retention":
                    return {"status": deletion.status, "attempt_count": deletion.attempt_count}
                if deletion.status not in {"queued", "failed", "running"}:
                    return {"status": deletion.status, "attempt_count": deletion.attempt_count}

                deletion.status = "running"
                deletion.attempt_count += 1
                deletion.retryable = False
                deletion.last_error_code = None
                counts = await delete_personal_learning_data(
                    db, user_id=deletion.subject_user_id
                )
                deletion.processed_counts = {
                    **(deletion.processed_counts or {}),
                    **counts,
                }
                deletion.retained_categories = RETAINED_CATEGORIES
                deletion.status = "completed_with_retention"
                deletion.retryable = False
                deletion.completed_at = datetime.now(UTC)
                db.add(
                    AuditLog(
                        actor_id=deletion.subject_user_id,
                        action="privacy.deletion.completed_with_retention",
                        resource_type="privacy_deletion_request",
                        resource_id=deletion.id,
                        detail={
                            "processed_counts": deletion.processed_counts,
                            "status": deletion.status,
                        },
                    )
                )
                await db.flush()
                return {"status": deletion.status, "attempt_count": deletion.attempt_count}
    except Exception:  # noqa: BLE001 - error details may include sensitive driver data
        async with session_factory() as db:
            async with db.begin():
                deletion = await db.scalar(
                    select(PrivacyDeletionRequest)
                    .where(PrivacyDeletionRequest.id == request_id)
                    .with_for_update()
                )
                # The processing transaction is atomic: a failed attempt leaves the
                # work item queued/failed and never publishes a partial completion.
                if deletion is not None and deletion.status != "completed_with_retention":
                    deletion.status = "failed"
                    deletion.attempt_count += 1
                    deletion.retryable = True
                    deletion.last_error_code = "deletion_processing_failed"
                    await db.flush()
                    return {
                        "status": deletion.status,
                        "attempt_count": deletion.attempt_count,
                    }
        return {"status": "not_found"}


@celery_app.task(
    name="privacy.deletion.execute",
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_privacy_deletion(request_id: str) -> dict[str, str | int]:
    """执行本地删除工作单；已完成单据重放为 no-op。"""
    return run_task(_execute_privacy_deletion(request_id))
