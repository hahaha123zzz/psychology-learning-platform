import asyncio

import pytest

from app.core.errors import ApiError
from app.modules.knowledge.domain import (
    classify_claim,
    validate_domain_pack_shape,
    verify_claim_with_bounded_retrieval,
)


def _pack() -> dict:
    return {
        "knowledge_points": [{"key": "kp-a", "title": "注意"}],
        "evidence_bindings": [{"key": "ev-a"}],
        "misconceptions": [
            {
                "key": "mis-a",
                "title": "误区",
                "definition": "研究者把相关误认为因果。",
                "conditions": "仅当观察性相关设计且未控制混淆时。",
                "knowledge_point_keys": ["kp-a"],
                "evidence_binding_keys": ["ev-a"],
            }
        ],
    }


def test_misconception_requires_falsifiable_definition_conditions_and_evidence() -> None:
    validate_domain_pack_shape(_pack())
    invalid = _pack()
    invalid["misconceptions"][0]["definition"] = " "
    with pytest.raises(ApiError) as caught:
        validate_domain_pack_shape(invalid)
    assert caught.value.code == "MISCONCEPTION_DEFINITION_INVALID"


def test_misconception_cannot_self_declare_canonical_or_use_missing_refs() -> None:
    invalid = _pack()
    invalid["misconceptions"][0]["canonical"] = True
    with pytest.raises(ApiError) as caught:
        validate_domain_pack_shape(invalid)
    assert caught.value.code == "MISCONCEPTION_CANONICAL_FORBIDDEN"

    invalid["misconceptions"][0].pop("canonical")
    invalid["misconceptions"][0]["evidence_binding_keys"] = ["missing"]
    with pytest.raises(ApiError) as caught:
        validate_domain_pack_shape(invalid)
    assert caught.value.code == "MISCONCEPTION_EVIDENCE_REQUIRED"


def test_claim_four_states_do_not_infer_contradiction_from_missing_overlap() -> None:
    assert classify_claim()["status"] == "unknown"
    assert classify_claim(supported_subclaims=["A"])["status"] == "supported"
    assert (
        classify_claim(supported_subclaims=["A"], unsupported_subclaims=["B"])["status"]
        == "partially-supported"
    )
    assert classify_claim(contradicted_subclaims=["A"])["status"] == "unknown"


def test_claim_contradiction_requires_a_resolvable_counterevidence_ref() -> None:
    scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}
    evidence = [{"evidence_id": "counter-1", "text": "synthetic content evidence"}]

    async def retrieve_once(_scope_snapshot):
        raise AssertionError("verified initial counterevidence must not trigger retrieval")

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=evidence,
            evaluate=lambda _claim, _items: {
                "status": "contradicted",
                "contradicted_subclaims": ["claim"],
                "counterevidence_refs": ["counter-1"],
            },
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert result["status"] == "contradicted"
    assert result["counterevidence_refs"] == ["counter-1"]


@pytest.mark.parametrize(
    ("counterevidence", "retrieval_scope"),
    [
        (
            {"counterevidence_scope_matches": True},
            {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"},
        ),
        (
            {"counterevidence_refs": ["not-in-evidence"]},
            {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"},
        ),
        (
            {"counterevidence_refs": ["learning-1"]},
            {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"},
        ),
        (
            {"counterevidence_refs": ["counter-1"]},
            {"course_id": "course-a", "publication_snapshot_id": "snapshot-other"},
        ),
    ],
)
def test_unverified_counterevidence_fails_closed_even_with_positive_result(
    counterevidence: dict, retrieval_scope: dict
) -> None:
    required_scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}
    evidence = [
        {"evidence_id": "counter-1", "text": "synthetic content evidence"},
        {
            "evidence_id": "learning-1",
            "question_version_id": "question-1",
            "knowledge_point": "synthetic point",
            "correct": False,
        },
    ]

    async def retrieve_once(_scope_snapshot):
        raise AssertionError("unverified counterevidence must stop before retry")

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=evidence,
            evaluate=lambda _claim, _items: {
                "status": "supported",
                "supported_subclaims": ["claim"],
                "contradicted_subclaims": ["claim"],
                **counterevidence,
            },
            retrieve_once=retrieve_once,
            retrieval_scope=retrieval_scope,
            required_scope=required_scope,
        )
    )
    assert result["status"] == "unknown"
    assert result["refusal_reason"] == "counterevidence_unverified"
    assert result["counterevidence_refs"] == []
    assert result["supplemental_retrieval_attempts"] == 0


@pytest.mark.parametrize(
    "counterevidence_fields",
    [
        {"counterevidence_scope_matches": True},
        {"counterevidence_refs": ["foreign-ref"]},
    ],
)
def test_contradicted_claim_without_verified_refs_is_unknown(
    counterevidence_fields: dict,
) -> None:
    scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}

    async def retrieve_once(_scope_snapshot):
        raise AssertionError("an unverified contradiction must stop before retry")

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[{"evidence_id": "content-ref", "text": "synthetic"}],
            evaluate=lambda _claim, _items: {
                "status": "contradicted",
                "contradicted_subclaims": ["claim"],
                **counterevidence_fields,
            },
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert result["status"] == "unknown"
    assert result["refusal_reason"] == "counterevidence_unverified"
    assert result["counterevidence_refs"] == []
    assert result["supplemental_retrieval_attempts"] == 0


def test_unverified_counterevidence_with_independent_partial_claim_stays_partial() -> None:
    scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}

    async def retrieve_once(_scope_snapshot):
        raise AssertionError("an unverified contradiction must stop before retry")

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[{"evidence_id": "content-ref", "text": "synthetic"}],
            evaluate=lambda _claim, _items: {
                "status": "partially-supported",
                "supported_subclaims": ["independently supported subclaim"],
                "unsupported_subclaims": ["independently unsupported subclaim"],
                "contradicted_subclaims": ["other subclaim"],
                "counterevidence_refs": ["foreign-ref"],
            },
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert result["status"] == "partially-supported"
    assert result["refusal_reason"] == "counterevidence_unverified"
    assert result["counterevidence_refs"] == []
    assert result["supplemental_retrieval_attempts"] == 0


def test_unverified_counterevidence_keeps_independent_partial_status() -> None:
    scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}

    async def retrieve_once(_scope_snapshot):
        raise AssertionError("unverified counterevidence must stop before retry")

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[{"evidence_id": "positive-1", "text": "synthetic"}],
            evaluate=lambda _claim, _items: {
                "status": "supported",
                "supported_subclaims": ["supported part"],
                "unsupported_subclaims": ["unsupported part"],
                "contradicted_subclaims": ["claim"],
                "counterevidence_refs": ["foreign-reference"],
            },
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert result["status"] == "partially-supported"
    assert result["supported_subclaims"] == ["supported part"]
    assert result["unsupported_subclaims"] == ["unsupported part"]
    assert result["contradicted_subclaims"] == []
    assert result["counterevidence_refs"] == []
    assert result["refusal_reason"] == "counterevidence_unverified"
    assert result["supplemental_retrieval_attempts"] == 0


def test_counterevidence_from_bounded_supplement_is_verified_against_combined_evidence() -> None:
    scope = {"course_id": "course-a", "publication_snapshot_id": "snapshot-a"}
    calls = 0

    async def retrieve_once(_scope_snapshot):
        nonlocal calls
        calls += 1
        return [{"evidence_id": "counter-2", "text": "synthetic supplemental content"}]

    def evaluate(_claim: str, items: list[dict]):
        if any(item.get("evidence_id") == "counter-2" for item in items):
            return {
                "status": "contradicted",
                "contradicted_subclaims": ["claim"],
                "counterevidence_refs": ["counter-2"],
            }
        return {"status": "unknown"}

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[{"evidence_id": "initial-1", "text": "synthetic"}],
            evaluate=evaluate,
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert calls == 1
    assert result["status"] == "contradicted"
    assert result["counterevidence_refs"] == ["counter-2"]
    assert result["supplemental_retrieval_attempts"] == 1


def test_claim_supplemental_retrieval_runs_at_most_once_and_keeps_scope() -> None:
    scope = {
        "user_id": "user-a",
        "organization_id": "org-a",
        "course_id": "course-a",
        "domain_release_id": "domain-a",
        "publication_snapshot_id": "snapshot-a",
        "material_version_ids": ["version-a"],
        "index_job_id": "job-a",
        "embedding_version": "embed-a",
    }
    calls = 0

    async def retrieve_once(scope_snapshot):
        nonlocal calls
        calls += 1
        assert scope_snapshot == scope
        return ["evidence-2"]

    def evaluate(_claim: str, evidence: list[str]):
        if "evidence-2" in evidence:
            return {"status": "supported", "supported_subclaims": ["claim"]}
        return {"status": "unknown"}

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=["evidence-1"],
            evaluate=evaluate,
            retrieve_once=retrieve_once,
            retrieval_scope=scope,
            required_scope=scope,
        )
    )
    assert calls == 1
    assert result["status"] == "supported"
    assert result["supplemental_retrieval_attempts"] == 1
    assert result["initial_evidence"] == ["evidence-1"]
    assert result["supplemental_evidence"] == ["evidence-2"]
    assert result["scope"] == scope


def test_claim_scope_change_blocks_supplemental_retrieval() -> None:
    calls = 0

    async def retrieve_once(_scope_snapshot):
        nonlocal calls
        calls += 1
        return ["should-not-run"]

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[],
            evaluate=lambda _claim, _evidence: {"status": "unknown"},
            retrieve_once=retrieve_once,
            retrieval_scope={"domain_release_id": "new"},
            required_scope={"domain_release_id": "old"},
        )
    )
    assert calls == 0
    assert result["status"] == "unknown"
    assert result["refusal_reason"] == "retrieval_scope_changed"
    assert result["supplemental_retrieval_attempts"] == 0


def test_claim_scope_requires_exact_snapshot_and_does_not_leak_mutations() -> None:
    calls = 0
    original_scope = {
        "organization_id": "org-a",
        "course_id": "course-a",
        "domain_release_id": "domain-a",
        "material_version_ids": ["version-a"],
    }

    async def retrieve_once(scope_snapshot):
        nonlocal calls
        calls += 1
        scope_snapshot["material_version_ids"].append("unbound-version")
        return ["supplemental"]

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[],
            evaluate=lambda _claim, evidence: (
                {"status": "supported", "supported_subclaims": ["claim"]}
                if "supplemental" in evidence
                else {"status": "unknown"}
            ),
            retrieve_once=retrieve_once,
            retrieval_scope=original_scope,
            required_scope={**original_scope, "user_id": "user-a"},
        )
    )
    assert calls == 0
    assert result["refusal_reason"] == "retrieval_scope_changed"
    assert result["supplemental_retrieval_attempts"] == 0

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[],
            evaluate=lambda _claim, evidence: (
                {"status": "supported", "supported_subclaims": ["claim"]}
                if "supplemental" in evidence
                else {"status": "unknown"}
            ),
            retrieve_once=retrieve_once,
            retrieval_scope=original_scope,
            required_scope={**original_scope},
        )
    )
    assert calls == 1
    assert result["scope"] == original_scope
    assert original_scope["material_version_ids"] == ["version-a"]


def test_claim_unknown_after_empty_supplemental_retrieval_is_explicitly_refused() -> None:
    calls = 0

    async def retrieve_once(_scope_snapshot):
        nonlocal calls
        calls += 1
        return []

    result = asyncio.run(
        verify_claim_with_bounded_retrieval(
            claim="claim",
            initial_evidence=[],
            evaluate=lambda _claim, _evidence: {"status": "unknown"},
            retrieve_once=retrieve_once,
            retrieval_scope={"course_id": "course-a"},
            required_scope={"course_id": "course-a"},
        )
    )
    assert calls == 1
    assert result["status"] == "unknown"
    assert result["refusal_reason"] == "insufficient_evidence"
    assert result["supplemental_evidence"] == []
    assert result["supplemental_retrieval_attempts"] == 1


def test_claim_rejects_evaluator_state_outside_four_state_contract() -> None:
    async def retrieve_once(_scope_snapshot):
        return []

    with pytest.raises(ValueError, match="one of the four Claim states"):
        asyncio.run(
            verify_claim_with_bounded_retrieval(
                claim="claim",
                initial_evidence=[],
                evaluate=lambda _claim, _evidence: {"status": "likely"},
                retrieve_once=retrieve_once,
                retrieval_scope={"course_id": "course-a"},
                required_scope={"course_id": "course-a"},
            )
        )


def test_domain_release_requires_independent_review_and_reviewed_manifest(client) -> None:
    from app.db.models import RoleAssignment
    from app.db.session import session_factory
    from tests.conftest import create_user_sync

    create_user_sync(email="domain-author@uni.edu", is_teacher=True)
    create_user_sync(email="domain-reviewer@uni.edu")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "domain-author@uni.edu", "password": "correct-password"},
    )
    assert response.status_code == 200
    course = client.post("/api/v1/courses", json={"title": "误区课程", "term": "2026秋"}).json()[
        "data"
    ]
    author_id = client.get("/api/v1/me").json()["data"]["id"]
    reviewer_login = client.post(
        "/api/v1/auth/login",
        json={"email": "domain-reviewer@uni.edu", "password": "correct-password"},
    )
    assert reviewer_login.status_code == 200
    reviewer_id = client.get("/api/v1/me").json()["data"]["id"]

    async def grant_publisher() -> None:
        async with session_factory() as db:
            db.add(
                RoleAssignment(
                    user_id=reviewer_id,
                    role="course_publisher",
                    scope_type="course",
                    scope_id=course["id"],
                )
            )
            await db.commit()

    asyncio.run(grant_publisher())
    author_login = client.post(
        "/api/v1/auth/login",
        json={"email": "domain-author@uni.edu", "password": "correct-password"},
    )
    assert author_login.status_code == 200
    assert client.get("/api/v1/me").json()["data"]["id"] == author_id
    pack = _pack()
    pack["evidence_bindings"] = [
        {
            "key": "ev-a",
            "object_key": "mis-a",
            "material_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "material_version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
            "source_object_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
        }
    ]
    created = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases",
        json={"manifest": {"domain_pack": pack}},
        headers={"Idempotency-Key": "domain-create-01"},
    )
    assert created.status_code == 201, created.text
    release_id = created.json()["data"]["id"]

    unreviewed_search = client.post(
        "/api/v1/knowledge/search",
        json={
            "course_id": course["id"],
            "query": "相关是否代表因果",
            "domain_release_id": release_id,
        },
    )
    assert unreviewed_search.status_code == 404, unreviewed_search.text
    assert unreviewed_search.json()["error"]["code"] == "DOMAIN_RELEASE_NOT_FOUND"

    self_review = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}/misconceptions/mis-a/review",
        json={"decision": "approved", "reason": "自审", "evidence_refs": ["ev-a"]},
        headers={"Idempotency-Key": "domain-review-self"},
    )
    assert self_review.status_code == 409, self_review.text
    assert self_review.json()["error"]["code"] == "DOMAIN_REVIEW_SELF_APPROVAL"

    client.post(
        "/api/v1/auth/login",
        json={"email": "domain-reviewer@uni.edu", "password": "correct-password"},
    )
    reviewed = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}/misconceptions/mis-a/review",
        json={"decision": "approved", "reason": "证据与范围已核对", "evidence_refs": ["ev-a"]},
        headers={"Idempotency-Key": "domain-review-01"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["decision"] == "approved"
    replayed = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}/misconceptions/mis-a/review",
        json={"decision": "approved", "reason": "证据与范围已核对", "evidence_refs": ["ev-a"]},
        headers={"Idempotency-Key": "domain-review-01"},
    )
    assert replayed.status_code == 200
    assert replayed.json()["meta"]["idempotent_replay"] is True
    assert replayed.json()["data"]["decision_id"] == reviewed.json()["data"]["decision_id"]
    conflict = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}/misconceptions/mis-a/review",
        json={"decision": "rejected", "reason": "不同请求", "evidence_refs": ["ev-a"]},
        headers={"Idempotency-Key": "domain-review-01"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    client.post(
        "/api/v1/auth/login",
        json={"email": "domain-author@uni.edu", "password": "correct-password"},
    )
    edited = dict(pack)
    edited["misconceptions"] = [dict(pack["misconceptions"][0], title="修改后的候选")]
    changed = client.patch(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}",
        json={"expected_version": 1, "manifest": {"domain_pack": edited}},
        headers={"Idempotency-Key": "domain-update-01"},
    )
    assert changed.status_code == 200, changed.text
    client.post(
        "/api/v1/auth/login",
        json={"email": "domain-reviewer@uni.edu", "password": "correct-password"},
    )
    published = client.post(
        f"/api/v1/courses/{course['id']}/domain-releases/{release_id}/publish",
        headers={"Idempotency-Key": "domain-publish-01"},
    )
    assert published.status_code == 409
    assert published.json()["error"]["code"] == "DOMAIN_MISCONCEPTION_REVIEW_REQUIRED"
