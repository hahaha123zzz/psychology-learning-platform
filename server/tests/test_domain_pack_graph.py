import asyncio

import pytest

from tests.conftest import create_user_sync


def _login(client, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-password"}
    )
    assert response.status_code == 200


def _valid_domain_pack() -> dict:
    return {
        "knowledge_points": [
            {"key": "kp-attention", "title": "注意"},
            {"key": "kp-perception", "title": "知觉"},
        ],
        "relations": [
            {
                "key": "relation-attention-perception",
                "source_key": "kp-attention",
                "target_key": "kp-perception",
                "relation_type": "prerequisite",
            }
        ],
        "experiments": [{"key": "experiment-stroop", "title": "Stroop 实验"}],
    }


def test_domain_pack_graph_accepts_declared_ids_and_directed_relation() -> None:
    from app.modules.courses.service import validate_course_release_pack

    validate_course_release_pack("domain_pack", _valid_domain_pack())


@pytest.mark.parametrize(
    ("pack", "expected_issue"),
    [
        (
            {
                "knowledge_points": [
                    {"key": "kp-1", "title": "注意"},
                    {"key": "kp-1", "title": "知觉"},
                ]
            },
            "DOMAIN_OBJECT_KEY_DUPLICATE",
        ),
        (
            {
                "knowledge_points": [{"key": "kp-1", "title": "注意"}],
                "relations": [
                    {
                        "key": "relation-missing-target",
                        "source_key": "kp-1",
                        "target_key": "kp-missing",
                        "relation_type": "prerequisite",
                    }
                ],
            },
            "DOMAIN_RELATION_TARGET_NOT_FOUND",
        ),
        (
            {
                "knowledge_points": [{"key": "kp-1", "title": "注意"}],
                "relations": [
                    {
                        "key": "relation-self",
                        "source_key": "kp-1",
                        "target_key": "kp-1",
                        "relation_type": "related",
                    }
                ],
            },
            "DOMAIN_RELATION_SELF_REFERENCE",
        ),
        (
            {
                "knowledge_points": [
                    {"key": "kp-1", "title": "注意"},
                    {"key": "kp-2", "title": "知觉"},
                ],
                "relations": [
                    {
                        "key": "relation-1",
                        "source_key": "kp-1",
                        "target_key": "kp-2",
                        "relation_type": "related",
                    },
                    {
                        "key": "relation-2",
                        "source_key": "kp-1",
                        "target_key": "kp-2",
                        "relation_type": "related",
                    },
                ],
            },
            "DOMAIN_RELATION_DUPLICATE",
        ),
        (
            {
                "knowledge_points": [{"key": " kp-1", "title": "注意"}],
            },
            "DOMAIN_OBJECT_KEY_NOT_CANONICAL",
        ),
        (
            {
                "knowledge_points": [{"key": "shared", "title": "注意"}],
                "experiments": [{"key": "shared", "title": "Stroop 实验"}],
            },
            "DOMAIN_OBJECT_KEY_DUPLICATE",
        ),
    ],
)
def test_domain_pack_graph_rejects_invalid_object_or_relation(pack, expected_issue) -> None:
    from app.core.errors import ApiError
    from app.modules.courses.service import validate_course_release_pack

    with pytest.raises(ApiError) as caught:
        validate_course_release_pack("domain_pack", pack)

    assert caught.value.status_code == 422
    assert caught.value.code == "RELEASE_DOMAIN_GRAPH_INVALID"
    assert expected_issue in {
        issue["code"] for issue in caught.value.details["issues"]
    }


def test_legacy_publish_cannot_bypass_controlled_release_request(client) -> None:
    from app.db.models import CourseRelease
    from app.db.session import session_factory

    create_user_sync(email="domain-graph-publish@uni.edu", is_teacher=True)
    _login(client, "domain-graph-publish@uni.edu")
    course = client.post(
        "/api/v1/courses",
        json={"title": "图校验课程", "term": "2026秋"},
    ).json()["data"]
    release_response = client.post(
        f"/api/v1/courses/{course['id']}/releases",
        json={"name": "领域草稿", "domain_pack": _valid_domain_pack()},
    )
    assert release_response.status_code == 201
    release_id = release_response.json()["data"]["id"]

    async def _write_legacy_invalid_pack() -> None:
        async with session_factory() as session:
            release = await session.get(CourseRelease, release_id)
            assert release is not None
            manifest = dict(release.manifest)
            manifest["domain_pack"] = {
                "knowledge_points": [{"key": "kp-1", "title": "注意"}],
                "relations": [
                    {
                        "key": "relation-legacy-dangling",
                        "source_key": "kp-1",
                        "target_key": "missing",
                        "relation_type": "prerequisite",
                    }
                ],
            }
            release.manifest = manifest
            await session.commit()

    asyncio.run(_write_legacy_invalid_pack())
    response = client.post(
        f"/api/v1/courses/{course['id']}/releases/{release_id}/publish"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RELEASE_PUBLISH_REQUEST_REQUIRED"
    current = client.get(
        f"/api/v1/courses/{course['id']}/releases/{release_id}/gate"
    )
    assert current.status_code == 200
    assert current.json()["data"]["can_publish"] is False
