from tests.conftest import create_user_sync, publish_course_release_for_test


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def test_teaching_asset_registry_validates_versions_and_rejects_unbound_refs(client) -> None:
    create_user_sync(email="asset-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="asset-student@uni.edu")
    _login(client, "asset-teacher@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "资产课程", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]
    course_id = course["id"]
    assert client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student"},
    ).status_code == 201
    release = client.post(
        f"/api/v1/courses/{course_id}/releases",
        json={"name": "资产版本", "material_ids": []},
    ).json()["data"]
    unsafe = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsafe-demo",
            "template": "explanation",
            "content": {"html": "<script>alert(1)</script>"},
            "fallback_text": "文字解释",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    executable_text = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsafe-uri",
            "template": "explanation",
            "content": {"title": "说明", "text": "javascript:alert(1)"},
            "fallback_text": "纯文本说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert executable_text.status_code == 422
    assert executable_text.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    markup_fallback = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "markup-fallback",
            "template": "explanation",
            "content": {"title": "说明", "text": "可读说明"},
            "fallback_text": "<strong>不可作为 HTML 的说明</strong>",
            "allowed_actions": ["SHOW"],
        },
    )
    assert markup_fallback.status_code == 422
    assert markup_fallback.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    unsupported_shape = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unsupported-shape",
            "template": "table",
            "content": {"title": "表格", "html": "<table><tr><td>x</td></tr></table>"},
            "fallback_text": "表格文字说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unsupported_shape.status_code == 422
    assert unsupported_shape.json()["error"]["code"] == "TEACHING_ASSET_UNSAFE_CONTENT"

    unknown_field = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "unknown-field",
            "template": "explanation",
            "content": {"title": "说明", "text": "可读说明", "src": "https://example.invalid"},
            "fallback_text": "纯文本说明",
            "allowed_actions": ["SHOW"],
        },
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["error"]["code"] == "TEACHING_ASSET_CONTENT_NOT_ALLOWED"

    created = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": "attention-explanation",
            "template": "explanation",
            "release_id": release["id"],
            "content": {"title": "观察结果", "text": "先描述差异，再说明证据边界。"},
            "fallback_text": "先描述差异，再说明证据边界。",
            "evidence_refs": ["object:demo:1"],
            "allowed_actions": ["SHOW", "HIGHLIGHT"],
        },
    )
    assert created.status_code == 201
    asset = created.json()["data"]
    assert asset["version_no"] == 1
    assert asset["status"] == "draft"

    edited = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets",
        json={
            "asset_key": asset["asset_key"],
            "template": asset["template"],
            "content": {"title": "修订后的观察结果", "text": "保留原版本并另建草稿。"},
            "fallback_text": "修订后的纯文本说明。",
            "evidence_refs": ["object:demo:1"],
            "allowed_actions": ["SHOW"],
        },
    )
    assert edited.status_code == 201
    assert edited.json()["data"]["version_no"] == 2
    listed = client.get(f"/api/v1/courses/{course_id}/teaching-assets").json()["data"]
    by_version = {row["version_no"]: row for row in listed}
    assert by_version[1]["content"]["title"] == "观察结果"
    assert by_version[2]["content"]["title"] == "修订后的观察结果"

    published_release = publish_course_release_for_test(client, course_id, release["id"])
    assert published_release["status"] == "published"

    _login(client, "asset-student@uni.edu")
    assert client.get(f"/api/v1/student/teaching-assets/{asset['id']}").status_code == 404

    _login(client, "asset-teacher@uni.edu")
    published = client.post(
        f"/api/v1/courses/{course_id}/teaching-assets/{asset['id']}/publish",
        json={"version": asset["version"], "release_id": release["id"]},
    )
    assert published.status_code == 409
    assert published.json()["error"]["code"] == "TEACHING_ASSET_EVIDENCE_UNBOUND"


def test_teaching_asset_publish_requires_target_release_binding_and_legacy_read_is_scoped(
    client,
) -> None:
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.models import CourseMember, CourseRelease, TeachingAssetVersion
    from app.db.session import session_factory

    teacher_id = create_user_sync(email="asset-binding-teacher@uni.edu", is_teacher=True)
    student_id = create_user_sync(email="asset-binding-student@uni.edu")
    foreign_student_id = create_user_sync(email="asset-binding-foreign@uni.edu")
    _login(client, "asset-binding-teacher@uni.edu")
    course_id = client.post(
        "/api/v1/courses",
        json={"title": "Evidence 绑定课程", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]["id"]
    other_course_id = client.post(
        "/api/v1/courses",
        json={"title": "另一门课程", "term": "2026春", "timezone": "Asia/Shanghai"},
    ).json()["data"]["id"]
    membership = client.post(
        f"/api/v1/courses/{course_id}/members",
        json={"user_id": student_id, "role": "student"},
    )
    assert membership.status_code == 201, membership.text
    foreign_membership = client.post(
        f"/api/v1/courses/{other_course_id}/members",
        json={"user_id": foreign_student_id, "role": "student"},
    )
    assert foreign_membership.status_code == 201, foreign_membership.text

    target_key = "binding:target-release"
    other_release_key = "binding:other-release"

    async def seed_releases_and_legacy_asset() -> tuple[str, str, str]:
        async with session_factory() as db:
            releases = []
            for version_no, binding_key in ((1, target_key), (2, other_release_key)):
                release = CourseRelease(
                    course_id=course_id,
                    version_no=version_no,
                    name=f"合成课程版本 {version_no}",
                    status="published",
                    manifest={
                        "domain_pack": {
                            "evidence_bindings": [
                                {
                                    "key": binding_key,
                                    "object_key": "kp-a",
                                    "material_id": "material-a",
                                    "material_version_id": "version-a",
                                    "source_object_id": "object-a",
                                }
                            ]
                        }
                    },
                    created_by=teacher_id,
                    published_by=teacher_id,
                    published_at=datetime.now(UTC),
                )
                db.add(release)
                await db.flush()
                releases.append(release)
            legacy = TeachingAssetVersion(
                course_id=course_id,
                release_id=releases[0].id,
                asset_key="legacy-empty-evidence",
                version_no=1,
                template="explanation",
                status="published",
                content={"title": "历史说明", "text": "保留可读的旧资产。"},
                fallback_text="历史说明纯文本。",
                evidence_refs=[],
                allowed_actions=["SHOW"],
                created_by=teacher_id,
                published_by=teacher_id,
                published_at=datetime.now(UTC),
            )
            db.add(legacy)
            await db.commit()
            return releases[0].id, releases[1].id, legacy.id

    target_release_id, second_release_id, legacy_asset_id = asyncio.run(
        seed_releases_and_legacy_asset()
    )

    def create_draft(asset_key: str, evidence_refs: list[str]) -> dict:
        response = client.post(
            f"/api/v1/courses/{course_id}/teaching-assets",
            json={
                "asset_key": asset_key,
                "template": "explanation",
                "content": {"title": asset_key, "text": "合成说明。"},
                "fallback_text": "合成说明纯文本。",
                "evidence_refs": evidence_refs,
                "allowed_actions": ["SHOW"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]

    def publish_draft(asset: dict, release_id: str):
        return client.post(
            f"/api/v1/courses/{course_id}/teaching-assets/{asset['id']}/publish",
            json={"version": asset["version"], "release_id": release_id},
        )

    unbound_cases = [
        ("empty-ref", [], "TEACHING_ASSET_EVIDENCE_REQUIRED", target_release_id),
        ("unknown-ref", ["binding:unknown"], "TEACHING_ASSET_EVIDENCE_UNBOUND", target_release_id),
        ("raw-object-id", ["object-a"], "TEACHING_ASSET_EVIDENCE_UNBOUND", target_release_id),
        (
            "other-release-ref",
            [other_release_key],
            "TEACHING_ASSET_EVIDENCE_UNBOUND",
            target_release_id,
        ),
    ]
    for asset_key, evidence_refs, error_code, release_id in unbound_cases:
        draft = create_draft(asset_key, evidence_refs)
        rejected = publish_draft(draft, release_id)
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["error"]["code"] == error_code

    valid = create_draft("bound-to-target-release", [target_key])
    published = publish_draft(valid, target_release_id)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["release_id"] == target_release_id

    _login(client, "asset-binding-student@uni.edu")
    legacy_read = client.get(f"/api/v1/student/teaching-assets/{legacy_asset_id}")
    assert legacy_read.status_code == 200, legacy_read.text
    assert legacy_read.json()["data"]["evidence_refs"] == []

    _login(client, "asset-binding-foreign@uni.edu")
    cross_course = client.get(f"/api/v1/student/teaching-assets/{legacy_asset_id}")
    assert cross_course.status_code == 404

    async def revoke_student() -> None:
        async with session_factory() as db:
            member = await db.scalar(
                select(CourseMember).where(
                    CourseMember.course_id == course_id,
                    CourseMember.user_id == student_id,
                )
            )
            assert member is not None
            member.status = "removed"
            await db.commit()

    asyncio.run(revoke_student())
    _login(client, "asset-binding-student@uni.edu")
    revoked = client.get(f"/api/v1/student/teaching-assets/{legacy_asset_id}")
    assert revoked.status_code == 404


def test_asset_evidence_refs_resolve_only_to_target_domain_pack_keys() -> None:
    import pytest

    from app.core.errors import ApiError
    from app.modules.teaching_assets.service import validate_evidence_refs_for_release

    manifest = {
        "domain_pack": {
            "evidence_bindings": [
                {
                    "key": "binding:current",
                    "object_key": "kp-a",
                    "source_object_id": "object-a",
                }
            ]
        }
    }
    validate_evidence_refs_for_release(evidence_refs=["binding:current"], release_manifest=manifest)
    for refs, expected_code in (
        ([], "TEACHING_ASSET_EVIDENCE_REQUIRED"),
        (["binding:unknown"], "TEACHING_ASSET_EVIDENCE_UNBOUND"),
        (["object-a"], "TEACHING_ASSET_EVIDENCE_UNBOUND"),
        (["binding:other-release"], "TEACHING_ASSET_EVIDENCE_UNBOUND"),
    ):
        with pytest.raises(ApiError) as exc_info:
            validate_evidence_refs_for_release(evidence_refs=refs, release_manifest=manifest)
        assert exc_info.value.code == expected_code
