import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.memory.service import (
    effective_memory_conditions,
    memory_items_detail,
    open_memory_conflict,
    record_memory_candidate,
    resolve_memory_conflict,
)
from app.modules.tutor.policy import resolve_effective_policy
from app.modules.tutor.service import (
    DomainClaimContext,
    verify_domain_claim_for_tutor,
)


def _claim_scope() -> dict:
    return {
        "user_id": "student-id",
        "organization_id": "organization-id",
        "course_id": "course-id",
        "class_id": "class-id",
        "course_release_assignment_id": "assignment-id",
        "course_release_id": "course-release-id",
        "domain_release_id": "domain-release-id",
        "publication_snapshot_id": "publication-snapshot-id",
        "material_version_ids": ["material-version-id"],
        "index_job_id": "index-job-id",
        "embedding_version": "embedding-v1",
        "publication_snapshots": [
            {
                "material_id": "material-id",
                "material_version_id": "material-version-id",
                "publication_snapshot_id": "publication-snapshot-id",
                "index_job_id": "index-job-id",
                "embedding_version": "embedding-v1",
                "domain_release_id": "domain-release-id",
            }
        ],
    }


def test_tutor_claim_persists_four_state_scope_and_initial_evidence_refs() -> None:
    async def run() -> None:
        scope = _claim_scope()
        retrieval_calls = 0

        async def retrieve(_scope: dict) -> list[dict]:
            nonlocal retrieval_calls
            retrieval_calls += 1
            return []

        def evaluate(_claim: str, evidence: list[dict]) -> dict:
            return {
                "status": "supported",
                "supported_subclaims": ["命题 A"],
                "evidence_ids": [item["evidence_id"] for item in evidence],
            }

        record = await verify_domain_claim_for_tutor(
            claim="命题 A",
            initial_evidence=[
                {"evidence_id": "evidence-1", "text": "敏感证据正文"},
                {"evidence_id": "evidence-1", "text": "重复引用"},
            ],
            context=DomainClaimContext(
                retrieval_scope=scope,
                required_scope=scope,
                evaluate=evaluate,
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == "supported"
        assert record["scope"] == scope
        assert record["retrieval_scope"] == scope
        assert record["initial_evidence_refs"] == ["evidence-1"]
        assert record["supplemental_evidence_refs"] == []
        assert record["supplemental_retrieval_attempts"] == 0
        assert record["refusal_reason"] is None
        assert "敏感证据正文" not in str(record)
        assert retrieval_calls == 0

    asyncio.run(run())


def test_tutor_claim_persists_one_supplemental_retrieval_and_evidence_ref() -> None:
    async def run() -> None:
        scope = _claim_scope()
        retrieval_scopes = []

        async def retrieve(actual_scope: dict) -> list[dict]:
            retrieval_scopes.append(actual_scope)
            actual_scope["material_version_ids"].append("callback-mutation")
            return [{"evidence_id": "evidence-2", "text": "补充证据正文"}]

        def evaluate(_claim: str, evidence: list[dict]) -> dict:
            if any(item["evidence_id"] == "evidence-2" for item in evidence):
                return {
                    "status": "supported",
                    "supported_subclaims": ["命题 B"],
                }
            return {"status": "unknown"}

        record = await verify_domain_claim_for_tutor(
            claim="命题 B",
            initial_evidence=[{"evidence_id": "evidence-1"}],
            context=DomainClaimContext(
                retrieval_scope=scope,
                required_scope=scope,
                evaluate=evaluate,
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == "supported"
        assert record["initial_evidence_refs"] == ["evidence-1"]
        assert record["supplemental_evidence_refs"] == ["evidence-2"]
        assert record["supplemental_retrieval_attempts"] == 1
        assert len(retrieval_scopes) == 1
        assert retrieval_scopes[0]["material_version_ids"] == [
            "material-version-id",
            "callback-mutation",
        ]
        assert record["scope"] == scope
        assert record["retrieval_scope"] == scope

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status", "result_fields"),
    [
        (
            "partially-supported",
            {
                "supported_subclaims": ["命题 F 的一部分"],
                "unsupported_subclaims": ["命题 F 的另一部分"],
            },
        ),
        (
            "contradicted",
            {
                "contradicted_subclaims": ["命题 G"],
                "counterevidence_scope_matches": True,
            },
        ),
    ],
)
def test_tutor_claim_persists_partial_and_contradicted_states(
    status: str, result_fields: dict
) -> None:
    async def run() -> None:
        scope = _claim_scope()

        async def retrieve(_scope: dict) -> list[dict]:
            return []

        record = await verify_domain_claim_for_tutor(
            claim="命题 F/G",
            initial_evidence=[{"evidence_id": "evidence-state"}],
            context=DomainClaimContext(
                retrieval_scope=scope,
                required_scope=scope,
                evaluate=lambda _claim, _evidence: {"status": status, **result_fields},
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == status
        assert record["supplemental_retrieval_attempts"] == 0
        if status == "partially-supported":
            assert record["supported_subclaims"] == ["命题 F 的一部分"]
            assert record["unsupported_subclaims"] == ["命题 F 的另一部分"]
            assert record["refusal_reason"] == "claim_partially_supported"
        else:
            assert record["contradicted_subclaims"] == ["命题 G"]
            assert record["refusal_reason"] == "claim_contradicted"

    asyncio.run(run())


def test_tutor_claim_scope_mismatch_blocks_retrieval_and_records_reason() -> None:
    async def run() -> None:
        required_scope = _claim_scope()
        retrieval_scope = {**required_scope, "index_job_id": "stale-index-job"}
        retrieval_calls = 0

        async def retrieve(_scope: dict) -> list[dict]:
            nonlocal retrieval_calls
            retrieval_calls += 1
            return []

        record = await verify_domain_claim_for_tutor(
            claim="命题 C",
            initial_evidence=[],
            context=DomainClaimContext(
                retrieval_scope=retrieval_scope,
                required_scope=required_scope,
                evaluate=lambda _claim, _evidence: {"status": "unknown"},
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == "unknown"
        assert record["refusal_reason"] == "retrieval_scope_changed"
        assert record["supplemental_retrieval_attempts"] == 0
        assert record["scope"] == required_scope
        assert record["retrieval_scope"] == retrieval_scope
        assert retrieval_calls == 0

    asyncio.run(run())


def test_tutor_claim_unknown_after_single_retrieval_is_explicitly_refused() -> None:
    async def run() -> None:
        scope = _claim_scope()
        retrieval_calls = 0

        async def retrieve(_scope: dict) -> list[dict]:
            nonlocal retrieval_calls
            retrieval_calls += 1
            return []

        record = await verify_domain_claim_for_tutor(
            claim="命题 D",
            initial_evidence=[],
            context=DomainClaimContext(
                retrieval_scope=scope,
                required_scope=scope,
                evaluate=lambda _claim, _evidence: {"status": "unknown"},
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == "unknown"
        assert record["refusal_reason"] == "insufficient_evidence"
        assert record["supplemental_retrieval_attempts"] == 1
        assert retrieval_calls == 1

    asyncio.run(run())


def test_tutor_claim_rejects_incomplete_snapshot_scope_before_retrieval() -> None:
    async def run() -> None:
        scope = _claim_scope()
        del scope["publication_snapshot_id"]
        retrieval_calls = 0

        async def retrieve(_scope: dict) -> list[dict]:
            nonlocal retrieval_calls
            retrieval_calls += 1
            return []

        with pytest.raises(ValueError, match="不可变发布快照字段"):
            await verify_domain_claim_for_tutor(
                claim="命题 E",
                initial_evidence=[],
                context=DomainClaimContext(
                    retrieval_scope=scope,
                    required_scope=scope,
                    evaluate=lambda _claim, _evidence: {"status": "unknown"},
                    retrieve_once=retrieve,
                ),
            )
        assert retrieval_calls == 0

    asyncio.run(run())


def test_tutor_claim_persists_timeout_reason_and_single_attempt() -> None:
    async def run() -> None:
        scope = _claim_scope()
        retrieval_calls = 0

        async def retrieve(_scope: dict) -> list[dict]:
            nonlocal retrieval_calls
            retrieval_calls += 1
            raise TimeoutError

        record = await verify_domain_claim_for_tutor(
            claim="命题 H",
            initial_evidence=[],
            context=DomainClaimContext(
                retrieval_scope=scope,
                required_scope=scope,
                evaluate=lambda _claim, _evidence: {"status": "unknown"},
                retrieve_once=retrieve,
            ),
        )
        assert record["status"] == "unknown"
        assert record["refusal_reason"] == "claim_verification_timeout"
        assert record["supplemental_retrieval_attempts"] == 1
        assert retrieval_calls == 1

    asyncio.run(run())


def test_effective_policy_only_tightens_and_records_sources() -> None:
    policy = resolve_effective_policy(
        [
            {"source": "system", "version": "v1", "policy": {}},
            {
                "source": "course_release",
                "version": "release-2",
                "policy": {"allowed_actions": ["diagnose", "teach", "check", "pause"]},
            },
            {
                "source": "user_preference",
                "version": "preference-4",
                "policy": {"allowed_actions": ["diagnose", "pause"], "max_hints": 1},
            },
        ]
    )
    assert policy["allowed_actions"] == ["diagnose", "pause"]
    assert policy["max_hints"] == 1
    assert [source["source"] for source in policy["sources"]] == [
        "system",
        "course_release",
        "user_preference",
    ]
    assert len(policy["hash"]) == 64


def test_unknown_policy_fails_closed() -> None:
    policy = resolve_effective_policy(
        [{"source": "teacher", "version": "x", "policy": {"future_override": True}}]
    )
    assert policy["fail_closed"] is True
    assert policy["allowed_actions"] == ["handoff", "pause"]
    assert policy["max_hints"] == 0


def test_invalid_actions_and_boolean_hint_limit_fail_closed() -> None:
    policy = resolve_effective_policy(
        [
            {
                "source": "course_release",
                "version": "release-invalid",
                "policy": {"allowed_actions": ["teach", "future-action"], "max_hints": True},
            }
        ]
    )
    assert policy["fail_closed"] is True
    assert policy["allowed_actions"] == ["handoff", "pause"]
    assert policy["max_support_gradient"] == 0
    assert policy["max_hints"] == 0


def test_memory_validity_conditions_are_user_and_single_course_scoped() -> None:
    conditions = effective_memory_conditions(
        user_id="student-id", course_id="course-id", now=datetime.now(UTC)
    )
    rendered = " ".join(str(condition) for condition in conditions)
    assert "memory_items.user_id" in rendered
    assert "memory_items.course_id" in rendered
    assert "expires_at" in rendered
    assert "valid_from" in rendered
    assert "conflict_status" in rendered


def test_memory_candidate_rejects_partial_turn_before_database_write() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="未完成"):
            await record_memory_candidate(
                None,
                user_id="student-id",
                course_id="course-id",
                layer="L1",
                kind="preference",
                content="示例",
                source_type="tutor",
                source_ref="turn-id",
                provenance_level="inferred",
                evidence_refs=["evidence-id"],
                confidence=0.5,
                source_completed=False,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )

    asyncio.run(run())


def test_inferred_memory_candidate_requires_evidence_before_database_write() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="证据引用"):
            await record_memory_candidate(
                None,
                user_id="student-id",
                course_id="course-id",
                layer="L1",
                kind="weakness",
                content="待复核的弱点",
                source_type="quiz",
                source_ref="attempt-id",
                provenance_level="inferred",
                evidence_refs=[],
                confidence=0.5,
                source_completed=True,
            )

    asyncio.run(run())


def test_memory_conflict_retains_both_sides_until_owner_resolves(client) -> None:
    from app.db.base import new_ulid
    from app.db.models import AuditLog, MemoryItem
    from app.db.session import session_factory
    from tests.test_materials import _setup_course

    course_id, student_id = _setup_course(client)
    first_id = new_ulid()
    second_id = new_ulid()

    async def run() -> None:
        async with session_factory() as db:
            db.add_all(
                [
                    MemoryItem(
                        id=first_id,
                        user_id=student_id,
                        course_id=course_id,
                        layer="L1",
                        kind="preference",
                        content="偏好简短提示",
                        source_type="user",
                        provenance_level="explicit",
                        evidence_refs=[],
                        confidence=0.7,
                    ),
                    MemoryItem(
                        id=second_id,
                        user_id=student_id,
                        course_id=course_id,
                        layer="L1",
                        kind="preference",
                        content="偏好详细提示",
                        source_type="user",
                        provenance_level="explicit",
                        evidence_refs=[],
                        confidence=0.7,
                        expires_at=datetime.now(UTC) - timedelta(days=1),
                    ),
                ]
            )
            await db.commit()
            group_id = await open_memory_conflict(
                db,
                user_id=student_id,
                course_id=course_id,
                first_memory_id=first_id,
                second_memory_id=second_id,
                reason="记录间偏好相反",
            )
            await db.commit()
            assert await memory_items_detail(
                db, user_id=student_id, course_id=course_id, layer=None, limit=20
            ) == []
            result = await resolve_memory_conflict(
                db,
                owner_user_id=student_id,
                course_id=course_id,
                conflict_group_id=group_id,
                keep_memory_id=first_id,
                actor_user_id=student_id,
                reason="当前由学生确认简短提示更合适",
            )
            await db.commit()
            visible = await memory_items_detail(
                db, user_id=student_id, course_id=course_id, layer=None, limit=20
            )
            assert result["resolved_count"] == 2
            assert [item["id"] for item in visible] == [first_id]
            assert visible[0]["conflict_status"] == "resolved"
            assert visible[0]["expires_at"] is None
            audit_rows = list(
                (await db.execute(
                    select(AuditLog).where(
                        AuditLog.resource_id == group_id,
                        AuditLog.action == "memory.conflict.resolved",
                    )
                )).scalars()
            )
            assert len(audit_rows) == 1

    asyncio.run(run())
