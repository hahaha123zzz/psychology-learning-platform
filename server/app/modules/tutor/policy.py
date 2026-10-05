"""Tutor、Branch 与题目教练共用的最严格教学策略解析。"""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Assessment,
    Attempt,
    CourseRelease,
    Intervention,
    InterventionRun,
    UserPreference,
)

TEACHING_ACTIONS = frozenset(
    {"diagnose", "teach", "check", "hint", "practice", "summarize", "pause", "handoff"}
)
POLICY_VERSION = "effective-policy.v1"


def resolve_effective_policy(layers: list[dict[str, Any]]) -> dict[str, Any]:
    """按层叠加限制；未知或格式错误的策略不扩大能力。"""
    allowed = set(TEACHING_ACTIONS)
    max_support = 3
    max_hints = 3
    sources: list[dict[str, str]] = []
    fail_closed = False

    for layer in layers:
        name = str(layer.get("source", "unknown"))
        version = str(layer.get("version", "unknown"))
        policy = layer.get("policy")
        sources.append({"source": name, "version": version})
        if policy is None:
            continue
        if not isinstance(policy, dict):
            fail_closed = True
            continue
        if set(policy) - {"allowed_actions", "max_support_gradient", "max_hints", "ai_support"}:
            fail_closed = True
        actions = policy.get("allowed_actions")
        if actions is not None:
            if not isinstance(actions, list) or any(
                not isinstance(action, str) or action not in TEACHING_ACTIONS
                for action in actions
            ):
                fail_closed = True
            else:
                allowed.intersection_update(actions)
        for field, current in (("max_support_gradient", max_support), ("max_hints", max_hints)):
            value = policy.get(field)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    fail_closed = True
                elif field == "max_support_gradient":
                    max_support = min(current, min(value, 3))
                else:
                    max_hints = min(current, min(value, 3))
        if policy.get("ai_support") is False:
            allowed.intersection_update({"pause", "handoff"})

    if fail_closed:
        allowed.intersection_update({"pause", "handoff"})
        max_support = 0
        max_hints = 0
    canonical = json.dumps(
        {"version": POLICY_VERSION, "layers": sources, "allowed": sorted(allowed),
         "max_support": max_support, "max_hints": max_hints, "fail_closed": fail_closed},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "version": POLICY_VERSION,
        "hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "allowed_actions": sorted(allowed),
        "max_support_gradient": max_support,
        "max_hints": max_hints,
        "sources": sources,
        "fail_closed": fail_closed,
    }


async def load_effective_policy(
    db: AsyncSession,
    *,
    user_id: str,
    course_id: str,
    assessment_id: str | None = None,
    course_release_id: str | None = None,
) -> dict[str, Any]:
    """读取各来源时先限定课程与当前用户 Scope，域对象只作为已发布快照输入。"""
    layers: list[dict[str, Any]] = [
        {"source": "system", "version": POLICY_VERSION, "policy": {}}
    ]

    attempt_query = (
        select(Assessment.id, Assessment.ai_policy, Assessment.version)
        .join(Attempt, Attempt.assessment_id == Assessment.id)
        .where(
            Attempt.user_id == user_id,
            Attempt.status == "in_progress",
            Assessment.course_id == course_id,
        )
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .limit(1)
    )
    if assessment_id:
        attempt_query = attempt_query.where(Assessment.id == assessment_id)
    attempt_assessment = (await db.execute(attempt_query)).one_or_none()
    if attempt_assessment is not None:
        assessment_id_value, _, assessment_version = attempt_assessment
        assessment_actions = {"pause", "handoff"}
        layers.append(
            {
                "source": "active_assessment",
                "version": f"{assessment_id_value}:{assessment_version}",
                "policy": {"allowed_actions": sorted(assessment_actions), "max_hints": 0},
            }
        )
    elif assessment_id:
        assessment = (
            await db.execute(
                select(Assessment.id, Assessment.ai_policy, Assessment.version).where(
                    Assessment.id == assessment_id,
                    Assessment.course_id == course_id,
                    Assessment.status == "published",
                )
            )
        ).one_or_none()
        if assessment is not None and assessment[1] == "disabled":
            layers.append(
                {
                    "source": "assessment",
                    "version": f"{assessment[0]}:{assessment[2]}",
                    "policy": {"allowed_actions": ["pause", "handoff"], "max_hints": 0},
                }
            )

    release_query = select(
        CourseRelease.id, CourseRelease.version_no, CourseRelease.manifest
    ).where(
        CourseRelease.course_id == course_id,
        CourseRelease.status.in_(("published", "deprecated")),
    )
    if course_release_id is not None:
        release_query = release_query.where(CourseRelease.id == course_release_id)
    else:
        release_query = release_query.order_by(
            CourseRelease.version_no.desc(), CourseRelease.id.desc()
        )
    release = (await db.execute(release_query.limit(1))).one_or_none()
    if release is not None:
        release_id, release_version, release_manifest = release
        policy = (release_manifest or {}).get("teaching_policy")
        if policy is not None:
            layers.append(
                {
                    "source": "course_release",
                    "version": f"{release_id}:{release_version}",
                    "policy": policy,
                }
            )
    elif course_release_id is not None:
        layers.append(
            {
                "source": "course_release_snapshot_missing",
                "version": course_release_id,
                "policy": {"unresolved_release_snapshot": True},
            }
        )

    active_intervention = (
        await db.execute(
            select(Intervention.id, Intervention.plan)
            .join(InterventionRun, InterventionRun.intervention_id == Intervention.id)
            .where(
                Intervention.course_id == course_id,
                InterventionRun.user_id == user_id,
                InterventionRun.status == "in_progress",
                Intervention.status == "active",
            )
            .order_by(InterventionRun.updated_at.desc(), InterventionRun.id.desc())
            .limit(1)
        )
    ).one_or_none()
    if active_intervention is not None:
        intervention_id, intervention_plan = active_intervention
        policy = (intervention_plan or {}).get("teaching_policy")
        if policy is not None:
            layers.append(
                {"source": "intervention", "version": intervention_id, "policy": policy}
            )

    preference = (
        await db.execute(
            select(UserPreference.id, UserPreference.version, UserPreference.preferences)
            .where(UserPreference.user_id == user_id)
            .limit(1)
        )
    ).one_or_none()
    preference_policy = (preference[2] or {}).get("teaching_policy") if preference else None
    if preference_policy is not None:
        layers.append(
            {
                "source": "user_preference",
                "version": f"{preference[0]}:{preference[1]}",
                "policy": preference_policy,
            }
        )
    return resolve_effective_policy(layers)
