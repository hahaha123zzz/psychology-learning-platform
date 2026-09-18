import json

from tests.test_materials import _login, _setup_course, _upload
from tests.test_search import TWO_CHAPTER_PDF


def _prepare(client, *, publish=True):
    course_id, student_id = _setup_course(client)
    upload = _upload(client, course_id, content=TWO_CHAPTER_PDF)
    version_id = upload.json()["data"]["version_id"]
    for kind in ("parse", "embed"):
        response = client.post(f"/api/v1/material-versions/{version_id}/{kind}")
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        import time

        deadline = time.time() + 20
        while time.time() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if job["status"] in ("succeeded", "failed"):
                assert job["status"] == "succeeded", job
                break
            time.sleep(0.3)
    if publish:
        assert (
            client.post(f"/api/v1/material-versions/{version_id}/publish").status_code
            == 200
        )
    return course_id, student_id, version_id


def _parse_sse_events(line_bytes: bytes) -> list[tuple[str, dict]]:
    events = []
    for block in line_bytes.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_name and data is not None:
            events.append((event_name, data))
    return events


def test_chat_session_creation_validates_mode_context(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    tutor_without_chapter = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "tutor"},
    )
    assert tutor_without_chapter.status_code == 422
    qa = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa", "title": "答疑"},
    )
    assert qa.status_code == 201
    assert qa.json()["data"]["mode"] == "course_qa"


def test_turn_stream_answers_with_citations_and_persists(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]

    turn = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "between subjects design 是什么？",
            "client_turn_id": "turn-abc-0001",
        },
    )
    assert turn.status_code == 200
    assert turn.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(turn.content)
    names = [name for name, _ in events]
    assert "state" in names
    assert "citation" in names
    assert "delta" in names
    done = [data for name, data in events if name == "done"][0]
    assert done["saved"] is True
    assert done["refusal"] is False

    detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    turns = detail.json()["data"]["turns"]
    assert [t["role"] for t in turns] == ["student", "tutor"]
    assert turns[1]["citations"]
    assert turns[1]["verification"]["claims"]


def test_turn_duplicate_client_turn_id_rejected(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    body = {"content": "你好", "client_turn_id": "turn-abc-0002"}
    first = client.post(f"/api/v1/chat/sessions/{session['id']}/turns", json=body)
    assert first.status_code == 200
    duplicate = client.post(f"/api/v1/chat/sessions/{session['id']}/turns", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TURN_DUPLICATE"


def test_turn_without_evidence_refuses(client) -> None:
    course_id, _, _ = _prepare(client, publish=True)
    session = client.post(
        "/api/v1/chat/sessions",
        json={"course_id": course_id, "mode": "course_qa"},
    ).json()["data"]
    turn = client.post(
        f"/api/v1/chat/sessions/{session['id']}/turns",
        json={
            "content": "量子纠缠在超导实验中的应用 zzqq",
            "client_turn_id": "turn-abc-0003",
        },
    )
    events = _parse_sse_events(turn.content)
    done = [data for name, data in events if name == "done"][0]
    assert done["refusal"] is True
    detail = client.get(f"/api/v1/chat/sessions/{session['id']}")
    tutor_turn = detail.json()["data"]["turns"][1]
    assert tutor_turn["refusal"] is True
    assert "未找到足够依据" in tutor_turn["content"]


def test_learning_session_state_machine_flow(client) -> None:
    course_id, _, version_id = _prepare(client, publish=True)
    _login(client, "ms@uni.edu")
    outline = client.get(f"/api/v1/material-versions/{version_id}/outline")
    chapter_id = outline.json()["data"][0]["id"]
    created_by_student = client.post(
        "/api/v1/learning-sessions",
        json={
            "course_id": course_id,
            "material_version_id": version_id,
            "chapter_object_id": chapter_id,
        },
    )
    assert created_by_student.status_code == 201
    learning = created_by_student.json()["data"]
    assert learning["state"] == "diagnose"
    assert learning["action"] == "wait_for_student"

    _login(client, "ms@uni.edu")
    stale = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": 99, "content": "完全不懂"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"

    response = client.post(
        f"/api/v1/learning-sessions/{learning['id']}/responses",
        json={"state_version": learning["state_version"], "content": "继续"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] in ("teach", "check")
    assert data["message"]

    current = client.get(f"/api/v1/learning-sessions/{learning['id']}")
    assert current.json()["data"]["state_version"] == learning["state_version"] + 1
