import asyncio

from app.db.models import (
    DomainRelease,
    Job,
    Material,
    MaterialVersion,
    PublicationSnapshot,
)
from app.db.session import session_factory
from tests.conftest import create_user_sync, publish_course_release_for_test


def _login(client, email: str):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-password"},
    )
    assert response.status_code == 200, response.text
    return response


def _create_course(client) -> dict:
    response = client.post(
        "/api/v1/courses",
        json={"title": "实验心理学", "term": "2026春", "timezone": "Asia/Shanghai"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _create_release(client, course_id: str, name: str, chapters: list[str] | None = None) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": name,
            "material_ids": [],
            "domain_pack": {"chapters": chapters or ["intro"]},
            "pedagogy_pack": {"tasks": ["predict"]},
            "assessment_pack": {"release_ids": []},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _publish(client, course_id: str, release_id: str) -> dict:
    return publish_course_release_for_test(client, course_id, release_id)


def test_course_release_pins_only_the_selected_published_domain_pack(client) -> None:
    author_id = create_user_sync(email="release-domain-binding-r3@uni.edu", is_teacher=True)
    _login(client, "release-domain-binding-r3@uni.edu")
    course = _create_course(client)
    course_id = course["id"]
    pack = {"knowledge_points": [{"key": "kp-a", "title": "注意"}]}

    async def seed_published_domain() -> str:
        async with session_factory() as db:
            domain_release = DomainRelease(
                course_id=course_id,
                version_no=1,
                manifest={"domain_pack": pack},
                pack_sha256="a" * 64,
                status="published",
                created_by=author_id,
                published_by=author_id,
            )
            db.add(domain_release)
            await db.commit()
            return domain_release.id

    domain_release_id = asyncio.run(seed_published_domain())
    created = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={"name": "引用领域快照", "domain_release_id": domain_release_id},
    )
    assert created.status_code == 201, created.text
    release = created.json()["data"]
    assert release["domain_release_id"] == domain_release_id
    assert release["manifest"]["domain_pack"] == pack

    mismatched = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={
            "name": "拒绝混用领域内容",
            "domain_release_id": domain_release_id,
            "domain_pack": {"chapters": ["different-pack"]},
        },
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["error"]["code"] == "RELEASE_DOMAIN_SNAPSHOT_MISMATCH"

    unbound = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={"name": "待绑定领域草稿", "domain_pack": pack},
    )
    assert unbound.status_code == 201, unbound.text
    unbound_release = unbound.json()["data"]
    assert unbound_release["domain_release_id"] is None
    gate = client.get(
        f"/api/v1/courses/{course_id}/releases/{unbound_release['id']}/gate"
    )
    assert "RELEASE_DOMAIN_SNAPSHOT_REQUIRED" in {
        issue["code"] for issue in gate.json()["data"]["errors"]
    }

    linked = client.patch(
        f"/api/v1/courses/{course_id}/releases/{unbound_release['id']}",
        json={"version": unbound_release["version"], "domain_release_id": domain_release_id},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["data"]["domain_release_id"] == domain_release_id
    assert linked.json()["data"]["manifest"]["domain_pack"] == pack


def test_legacy_publish_without_contract_is_rejected(client) -> None:
    create_user_sync(email="release-legacy-publish-r3@uni.edu", is_teacher=True)
    _login(client, "release-legacy-publish-r3@uni.edu")
    course = _create_course(client)
    release = _create_release(client, course["id"], "必须走受控发布")

    response = client.post(
        f"/api/v1/courses/{course['id']}/releases/{release['id']}/publish"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"
    gate = client.get(
        f"/api/v1/courses/{course['id']}/releases/{release['id']}/gate"
    )
    assert gate.status_code == 200
    assert gate.json()["data"]["can_publish"] is False


def test_course_release_pins_publication_snapshot_and_requires_explicit_reselection(client) -> None:
    author_id = create_user_sync(email="release-publication-pin-r3@uni.edu", is_teacher=True)
    _login(client, "release-publication-pin-r3@uni.edu")
    course = _create_course(client)
    course_id = course["id"]

    async def seed_publication() -> tuple[str, str, str, str]:
        async with session_factory() as db:
            material = Material(
                course_id=course_id,
                title="合成工程测试材料",
                material_type="textbook",
                visibility="published",
                status="active",
                created_by=author_id,
            )
            db.add(material)
            await db.flush()
            version = MaterialVersion(
                material_id=material.id,
                version_no=1,
                status="parsed",
                created_by=author_id,
            )
            db.add(version)
            await db.flush()
            material.current_version_id = version.id
            job = Job(
                kind="material_embed",
                status="succeeded",
                progress=100,
                payload={"material_version_id": version.id},
                created_by=author_id,
            )
            db.add(job)
            await db.flush()
            snapshot = PublicationSnapshot(
                material_id=material.id,
                material_version_id=version.id,
                index_job_id=job.id,
                embedding_version="test-embedding-v1",
                published_by=author_id,
            )
            db.add(snapshot)
            await db.commit()
            return material.id, version.id, job.id, snapshot.id

    material_id, first_version_id, first_job_id, first_snapshot_id = asyncio.run(seed_publication())
    created = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={"name": "固定资料快照", "material_ids": [material_id]},
    )
    assert created.status_code == 201, created.text
    release = created.json()["data"]
    assert release["manifest"]["material_version_ids"] == [first_version_id]
    assert release["manifest"]["publication_snapshots"] == [
        {
            "material_id": material_id,
            "material_version_id": first_version_id,
            "publication_snapshot_id": first_snapshot_id,
            "index_job_id": first_job_id,
            "embedding_version": "test-embedding-v1",
            "domain_release_id": None,
        }
    ]

    async def supersede_with_new_publication() -> tuple[str, str]:
        async with session_factory() as db:
            material = await db.get(Material, material_id)
            first_snapshot = await db.get(PublicationSnapshot, first_snapshot_id)
            assert material is not None and first_snapshot is not None
            first_snapshot.superseded_at = first_snapshot.published_at
            version = MaterialVersion(
                material_id=material_id,
                version_no=2,
                status="parsed",
                created_by=author_id,
            )
            db.add(version)
            await db.flush()
            material.current_version_id = version.id
            job = Job(
                kind="material_embed",
                status="succeeded",
                progress=100,
                payload={"material_version_id": version.id},
                created_by=author_id,
            )
            db.add(job)
            await db.flush()
            snapshot = PublicationSnapshot(
                material_id=material_id,
                material_version_id=version.id,
                index_job_id=job.id,
                embedding_version="test-embedding-v2",
                published_by=author_id,
            )
            db.add(snapshot)
            await db.commit()
            return version.id, snapshot.id

    second_version_id, second_snapshot_id = asyncio.run(supersede_with_new_publication())
    gate_url = f"/api/v1/courses/{course_id}/releases/{release['id']}/gate"
    stale_gate = client.get(gate_url)
    assert stale_gate.status_code == 200, stale_gate.text
    assert "RELEASE_MATERIAL_SNAPSHOT_STALE" in {
        item["code"] for item in stale_gate.json()["data"]["errors"]
    }

    metadata_update = client.patch(
        f"/api/v1/courses/{course_id}/releases/{release['id']}",
        json={"version": release["version"], "name": "元快照仍固定"},
    )
    assert metadata_update.status_code == 200, metadata_update.text
    assert metadata_update.json()["data"]["manifest"]["material_version_ids"] == [
        first_version_id
    ]
    assert metadata_update.json()["data"]["manifest"]["publication_snapshots"][0][
        "publication_snapshot_id"
    ] == first_snapshot_id

    reselected = client.patch(
        f"/api/v1/courses/{course_id}/releases/{release['id']}",
        json={"version": metadata_update.json()["data"]["version"], "material_ids": [material_id]},
    )
    assert reselected.status_code == 200, reselected.text
    assert reselected.json()["data"]["manifest"]["material_version_ids"] == [
        second_version_id
    ]
    assert reselected.json()["data"]["manifest"]["publication_snapshots"][0][
        "publication_snapshot_id"
    ] == second_snapshot_id


def test_release_preview_review_gate_and_stale_review(client) -> None:
    create_user_sync(email="release-author-r3@uni.edu", is_teacher=True)
    publisher_id = create_user_sync(email="release-publisher-r3@uni.edu")
    _login(client, "release-author-r3@uni.edu")
    course = _create_course(client)
    course_id = course["id"]

    release = _create_release(client, course_id, "审核版本")
    preview = client.get(f"/api/v1/courses/{course_id}/releases/{release['id']}/preview")
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["release"]["id"] == release["id"]
    assert len(preview_data["manifest_sha256"]) == 64

    gate_url = f"/api/v1/courses/{course_id}/releases/{release['id']}/gate"
    blocked = client.get(gate_url)
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["data"]["can_publish"] is False
    assert "RELEASE_REVIEW_REQUIRED" in {item["code"] for item in blocked.json()["data"]["errors"]}

    self_review = client.post(
        f"/api/v1/courses/{course_id}/releases/{release['id']}/reviews",
        headers={"Idempotency-Key": "r3-release-self-review"},
        json={
            "expected_version": release["version"],
            "manifest_sha256": preview_data["manifest_sha256"],
            "decision": "approved",
            "reason": "作者不能自审",
        },
    )
    assert self_review.status_code == 403
    assert self_review.json()["error"]["code"] == "RELEASE_SELF_REVIEW"

    import asyncio

    from app.db.models import RoleAssignment
    from app.db.session import session_factory

    async def grant_publisher() -> None:
        async with session_factory() as session:
            session.add(
                RoleAssignment(
                    user_id=publisher_id,
                    role="course_publisher",
                    scope_type="course",
                    scope_id=course_id,
                    status="active",
                    granted_by=release["created_by"],
                )
            )
            await session.commit()

    asyncio.run(grant_publisher())
    _login(client, "release-publisher-r3@uni.edu")
    review_url = f"/api/v1/courses/{course_id}/releases/{release['id']}/reviews"
    review_body = {
        "expected_version": release["version"],
        "manifest_sha256": preview_data["manifest_sha256"],
        "decision": "approved",
        "reason": "来源和结构检查通过",
    }
    headers = {"Idempotency-Key": "r3-release-review-approval"}
    reviewed = client.post(review_url, headers=headers, json=review_body)
    assert reviewed.status_code == 201, reviewed.text
    replay = client.post(review_url, headers=headers, json=review_body)
    assert replay.status_code == 201, replay.text
    assert replay.json()["meta"]["idempotent_replay"] is True
    passed = client.get(gate_url)
    assert passed.status_code == 200, passed.text
    assert passed.json()["data"]["can_publish"] is True

    _login(client, "release-author-r3@uni.edu")
    updated = client.patch(
        f"/api/v1/courses/{course_id}/releases/{release['id']}",
        json={"version": release["version"], "name": "审核后修订"},
    )
    assert updated.status_code == 200, updated.text
    stale_gate = client.get(gate_url)
    assert stale_gate.status_code == 200, stale_gate.text
    assert stale_gate.json()["data"]["can_publish"] is False
    assert "RELEASE_REVIEW_REQUIRED" in {
        item["code"] for item in stale_gate.json()["data"]["errors"]
    }

    _login(client, "release-publisher-r3@uni.edu")
    current_preview = client.get(
        f"/api/v1/courses/{course_id}/releases/{release['id']}/preview"
    ).json()["data"]
    current_release = current_preview["release"]
    current_review = client.post(
        review_url,
        headers={"Idempotency-Key": "r3-release-review-revision"},
        json={
            "expected_version": current_release["version"],
            "manifest_sha256": current_preview["manifest_sha256"],
            "decision": "approved",
            "reason": "复核修订后的当前版本",
        },
    )
    assert current_review.status_code == 201, current_review.text
    publish_url = f"/api/v1/courses/{course_id}/releases/{release['id']}/publish"
    publish_body = {"expected_version": current_release["version"]}
    publish_headers = {"Idempotency-Key": "r3-release-publish-approved"}
    published = client.post(publish_url, headers=publish_headers, json=publish_body)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "published"
    publish_replay = client.post(publish_url, headers=publish_headers, json=publish_body)
    assert publish_replay.status_code == 200, publish_replay.text
    assert publish_replay.json()["meta"]["idempotent_replay"] is True


def test_release_diff_only_compares_published_immutable_versions(client) -> None:
    create_user_sync(email="release-diff-r3@uni.edu", is_teacher=True)
    _login(client, "release-diff-r3@uni.edu")
    course = _create_course(client)
    course_id = course["id"]
    first = _create_release(client, course_id, "版本一", ["intro"])
    draft_diff = client.get(
        f"/api/v1/courses/{course_id}/releases/{first['id']}/diff",
        params={"against_release_id": first["id"]},
    )
    assert draft_diff.status_code == 422

    _publish(client, course_id, first["id"])
    second = _create_release(client, course_id, "版本二", ["intro", "methods"])
    _publish(client, course_id, second["id"])
    diff = client.get(
        f"/api/v1/courses/{course_id}/releases/{first['id']}/diff",
        params={"against_release_id": second["id"]},
    )
    assert diff.status_code == 200, diff.text
    changes = diff.json()["data"]["changes"]
    assert {item["kind"] for item in changes} == {"changed"}
    assert any(item["path"] == "/manifest/domain_pack/chapters" for item in changes)


def test_class_release_assignment_is_versioned_atomic_and_idempotent(client) -> None:
    create_user_sync(email="release-assignment-r3@uni.edu", is_teacher=True)
    _login(client, "release-assignment-r3@uni.edu")
    course = _create_course(client)
    course_id = course["id"]
    class_response = client.post(
        f"/api/v1/courses/{course_id}/classes",
        json={"code": "R3-1", "name": "实验班"},
    )
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["data"]["id"]
    first = _create_release(client, course_id, "班级版本一")
    _publish(client, course_id, first["id"])

    assignment_url = f"/api/v1/courses/{course_id}/classes/{class_id}/release-assignment"
    body = {"course_release_id": first["id"], "expected_version": 0}
    headers = {"Idempotency-Key": "r3-class-release-first"}
    created = client.put(assignment_url, headers=headers, json=body)
    assert created.status_code == 200, created.text
    first_assignment = created.json()["data"]
    assert first_assignment["status"] == "active"
    replay = client.put(assignment_url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["meta"]["idempotent_replay"] is True
    impact = client.get(
        f"/api/v1/courses/{course_id}/releases/{first['id']}/impact",
        params={"class_id": class_id},
    )
    assert impact.status_code == 200, impact.text
    assert impact.json()["data"]["measurement_status"] == "not_measured"
    assert impact.json()["data"]["privacy_group_size"] is None
    assert impact.json()["data"]["suppressed_small_sample"] is True

    second = _create_release(client, course_id, "班级版本二")
    _publish(client, course_id, second["id"])
    changed = client.put(
        assignment_url,
        headers={"Idempotency-Key": "r3-class-release-second"},
        json={
            "course_release_id": second["id"],
            "expected_version": first_assignment["version"],
            "close_reason": "新版课程内容通过审核",
        },
    )
    assert changed.status_code == 200, changed.text
    new_assignment = changed.json()["data"]
    assert new_assignment["supersedes_id"] == first_assignment["id"]

    import asyncio

    from app.db.models import CourseReleaseAssignment
    from app.db.session import session_factory

    async def read_previous_status() -> str:
        async with session_factory() as session:
            row = await session.get(CourseReleaseAssignment, first_assignment["id"])
            return row.status

    assert asyncio.run(read_previous_status()) == "closed"
    current = client.get(assignment_url)
    assert current.status_code == 200
    assert current.json()["data"]["id"] == new_assignment["id"]
