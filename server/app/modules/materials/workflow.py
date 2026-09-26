from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import get_embedding_client
from app.db.models import (
    Job,
    Material,
    MaterialVersion,
    ParseReviewIssue,
    PublicationSnapshot,
)

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


def _job_data(job: Job | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "error": job.error,
        "retryable": job.retryable,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


async def _latest_job(db: AsyncSession, *, version_id: str, kind: str) -> Job | None:
    return (
        await db.execute(
            select(Job)
            .where(
                Job.kind == kind,
                Job.payload["material_version_id"].as_string() == version_id,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def build_workflow(
    db: AsyncSession, *, material: Material, version: MaterialVersion
) -> dict[str, Any]:
    parse_job = await _latest_job(db, version_id=version.id, kind="material_parse")
    index_job = await _latest_job(db, version_id=version.id, kind="material_embed")
    issue_rows = (
        await db.execute(
            select(ParseReviewIssue.severity, ParseReviewIssue.status, func.count())
            .where(ParseReviewIssue.material_version_id == version.id)
            .group_by(ParseReviewIssue.severity, ParseReviewIssue.status)
        )
    ).all()
    issue_counts = {
        "blocking_open": 0,
        "warning_open": 0,
        "info_open": 0,
        "resolved": 0,
    }
    for severity, status, count in issue_rows:
        if status == "open":
            issue_counts[f"{severity}_open"] = int(count)
        else:
            issue_counts["resolved"] += int(count)

    snapshot = (
        await db.execute(
            select(PublicationSnapshot)
            .where(
                PublicationSnapshot.material_id == material.id,
                PublicationSnapshot.superseded_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    embedding_version: str | None = None
    embedding_error: str | None = None
    indexed_chunks = 0
    try:
        embedding_version = get_embedding_client().version
        indexed_chunks = int(
            await db.scalar(
                text(
                    "SELECT count(*) FROM knowledge_chunks "
                    "WHERE material_version_id = :version_id "
                    "AND embedding_version = :embedding_version "
                    "AND embedding IS NOT NULL"
                ),
                {"version_id": version.id, "embedding_version": embedding_version},
            )
            or 0
        )
    except ValueError as exc:
        embedding_error = str(exc)

    blockers: list[dict[str, str]] = []
    actions: list[str] = []
    parse_active = parse_job is not None and parse_job.status not in TERMINAL_JOB_STATUSES
    index_active = index_job is not None and index_job.status not in TERMINAL_JOB_STATUSES
    is_published = (
        material.visibility == "published"
        and material.current_version_id == version.id
        and version.status == "parsed"
    )

    if is_published:
        state = "published"
    elif version.status == "uploading":
        state = "uploading"
    elif parse_active or version.status == "parsing":
        state = "parsing"
    elif version.status == "failed":
        state = "failed"
        actions.append("retry_parse")
        blockers.append(
            {
                "code": "PARSE_FAILED",
                "message": parse_job.error
                if parse_job and parse_job.error
                else "解析失败，请重试。",
            }
        )
    elif version.status == "uploaded":
        state = "uploaded"
        actions.append("start_parse")
    elif version.status != "parsed":
        state = "failed"
        blockers.append({"code": "INVALID_VERSION_STATUS", "message": "版本状态不可继续处理。"})
    elif issue_counts["blocking_open"]:
        state = "review_required"
        actions.append("review_issues")
        blockers.append(
            {
                "code": "QUALITY_REVIEW_REQUIRED",
                "message": f"仍有 {issue_counts['blocking_open']} 个阻塞问题，必须重新解析。",
            }
        )
    elif index_active:
        state = "indexing"
    elif embedding_error:
        state = "index_required"
        blockers.append({"code": "EMBEDDING_CONFIGURATION_INVALID", "message": embedding_error})
    elif indexed_chunks == 0:
        state = "index_required"
        actions.append("build_index")
        if index_job and index_job.status == "failed":
            blockers.append(
                {
                    "code": "INDEX_FAILED",
                    "message": index_job.error or "索引构建失败，请重试。",
                }
            )
    else:
        state = "ready_to_publish"
        actions.append("publish")

    if issue_counts["warning_open"]:
        blockers.append(
            {
                "code": "QUALITY_WARNING",
                "message": f"有 {issue_counts['warning_open']} 个警告待教师确认；警告不阻塞发布。",
            }
        )

    steps = [
        {
            "key": "upload",
            "status": "current" if state == "uploading" else "completed",
            "progress": 0 if state == "uploading" else 100,
        },
        {
            "key": "parse",
            "status": (
                "failed"
                if state == "failed"
                else "current"
                if state == "parsing"
                else "completed"
                if version.status == "parsed"
                else "pending"
            ),
            "progress": parse_job.progress
            if parse_job and state == "parsing"
            else (100 if version.status == "parsed" else 0),
        },
        {
            "key": "review",
            "status": "blocked"
            if state == "review_required"
            else "completed"
            if version.status == "parsed" and not issue_counts["blocking_open"]
            else "pending",
            "progress": 100
            if version.status == "parsed" and not issue_counts["blocking_open"]
            else 0,
        },
        {
            "key": "index",
            "status": "current"
            if state == "indexing"
            else "completed"
            if indexed_chunks
            else "pending",
            "progress": index_job.progress
            if index_job and state == "indexing"
            else (100 if indexed_chunks else 0),
        },
        {
            "key": "publish",
            "status": "completed"
            if state == "published"
            else "current"
            if state == "ready_to_publish"
            else "pending",
            "progress": 100 if state == "published" else 0,
        },
    ]

    return {
        "material_id": material.id,
        "version_id": version.id,
        "state": state,
        "steps": steps,
        "allowed_actions": actions,
        "blockers": blockers,
        "issue_counts": issue_counts,
        "embedding_version": embedding_version,
        "indexed_chunk_count": indexed_chunks,
        "parse_job": _job_data(parse_job),
        "index_job": _job_data(index_job),
        "publication": (
            {
                "id": snapshot.id,
                "material_version_id": snapshot.material_version_id,
                "embedding_version": snapshot.embedding_version,
                "published_at": snapshot.published_at.isoformat(),
            }
            if snapshot
            else None
        ),
    }
