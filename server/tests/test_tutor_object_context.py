"""Figure/Table Tutor context 的本地确定性合同测试。"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.db.models import ChatTurn, Material, MaterialVersion, PublicationSnapshot
from app.modules.tutor import service as tutor_service
from app.modules.tutor.router import (
    TurnCreate,
    _replay_saved_turn,
    _turn_idempotency_matches,
    _turn_selected_pointer_ids,
)


class _FakeDb:
    def __init__(self) -> None:
        self.rows = []

    def add(self, row) -> None:
        if isinstance(row, ChatTurn) and row.id is None:
            row.id = "01ARZ3NDEKTSV4RRFFQ69G5FAZ"
        self.rows.append(row)

    async def flush(self) -> None:
        return None

    async def refresh(self, row, attribute_names=None) -> None:
        return None

    async def commit(self) -> None:
        return None


class _PointerDb:
    def __init__(self, rows: dict[tuple[type, str], object]) -> None:
        self.rows = rows

    async def get(self, model: type, row_id: str):
        return self.rows.get((model, row_id))


def _release_pointer_fixture(
    *, object_type: str = "table", excerpt: str = "组别 | 均值\n实验组 | 4"
):
    pointer = SimpleNamespace(
        id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        course_id="course-1",
        material_id="material-1",
        material_version_id="version-1",
        source_object_id="object-1",
        object_type=object_type,
        excerpt=excerpt,
        material_title="合成教材",
        physical_page=3,
    )
    pin = {
        "material_id": pointer.material_id,
        "material_version_id": pointer.material_version_id,
        "publication_snapshot_id": "snapshot-1",
        "index_job_id": "index-job-1",
        "embedding_version": "hash-v1",
        "domain_release_id": None,
    }
    binding = SimpleNamespace(
        manifest={
            "materials": [pointer.material_id],
            "material_version_ids": [pointer.material_version_id],
            "publication_snapshots": [pin],
        },
        domain_release_id=None,
    )
    snapshot = SimpleNamespace(
        material_id=pointer.material_id,
        material_version_id=pointer.material_version_id,
        index_job_id=pin["index_job_id"],
        embedding_version=pin["embedding_version"],
        domain_release_id=None,
    )
    material = SimpleNamespace(
        id=pointer.material_id,
        course_id=pointer.course_id,
        status="active",
        visibility="published",
    )
    version = SimpleNamespace(
        id=pointer.material_version_id,
        material_id=pointer.material_id,
        status="parsed",
    )
    rows = {
        (tutor_service.EvidencePointer, pointer.id): pointer,
        (PublicationSnapshot, pin["publication_snapshot_id"]): snapshot,
        (Material, pointer.material_id): material,
        (MaterialVersion, pointer.material_version_id): version,
    }
    return pointer, binding, material, rows


def test_turn_create_pointer_contract_is_additive_and_limited_to_one() -> None:
    schema = TurnCreate.model_json_schema()
    property_schema = schema["properties"]["selected_evidence_pointer_ids"]["anyOf"][0]
    assert property_schema["maxItems"] == 1
    assert property_schema["items"]["minLength"] == 26
    assert property_schema["items"]["maxLength"] == 26
    assert TurnCreate(
        content="表格怎么读？",
        client_turn_id="turn-ctx-0001",
        selected_evidence_pointer_ids=["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
    )
    with pytest.raises(ValidationError):
        TurnCreate(
            content="表格怎么读？",
            client_turn_id="turn-ctx-0002",
            selected_evidence_pointer_ids=[
                "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "01ARZ3NDEKTSV4RRFFQ69G5FAW",
            ],
        )


def test_idempotency_binds_selected_pointer_ids() -> None:
    saved = ChatTurn(role="student", content="读表", citations=[
        {"evidence_pointer_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
    ])
    pointer_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    other_pointer_id = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    assert _turn_selected_pointer_ids(saved) == [pointer_id]
    assert _turn_idempotency_matches(
        saved, content="读表", selected_pointer_ids=[pointer_id]
    )
    assert not _turn_idempotency_matches(
        saved, content="读表", selected_pointer_ids=[other_pointer_id]
    )
    assert not _turn_idempotency_matches(saved, content="改问", selected_pointer_ids=[pointer_id])


def test_selected_pointer_requires_exact_release_pin_and_current_access(monkeypatch) -> None:
    pointer, binding, material, rows = _release_pointer_fixture()
    session_row = SimpleNamespace(mode="course_qa", status="active", course_id="course-1")

    async def authorized_scope(db, *, session_row, user_id):
        return binding

    monkeypatch.setattr(tutor_service, "authorize_chat_session_release_scope", authorized_scope)

    async def resolve(candidate_rows=rows):
        return await tutor_service.authorize_selected_table_pointer(
            _PointerDb(candidate_rows),
            session_row=session_row,
            user_id="student-1",
            pointer_id=pointer.id,
        )

    assert asyncio.run(resolve()) is pointer

    foreign_rows = dict(rows)
    foreign_pointer = SimpleNamespace(**vars(pointer))
    foreign_pointer.course_id = "another-course"
    foreign_rows[(tutor_service.EvidencePointer, pointer.id)] = foreign_pointer
    with pytest.raises(ApiError) as foreign_error:
        asyncio.run(resolve(foreign_rows))
    assert foreign_error.value.status_code == 404

    version_rows = dict(rows)
    mismatched_pointer = SimpleNamespace(**vars(pointer))
    mismatched_pointer.material_version_id = "01ARZ3NDEKTSV4RRFFQ69G5FAX"
    version_rows[(tutor_service.EvidencePointer, pointer.id)] = mismatched_pointer
    with pytest.raises(ApiError) as version_error:
        asyncio.run(resolve(version_rows))
    assert version_error.value.status_code == 404

    material.status = "archived"
    with pytest.raises(ApiError) as revoked_error:
        asyncio.run(resolve())
    assert revoked_error.value.status_code == 404


def test_empty_figure_pointer_is_authorized_only_as_location(monkeypatch) -> None:
    pointer, binding, _, rows = _release_pointer_fixture(object_type="figure", excerpt="")
    session_row = SimpleNamespace(mode="course_qa", status="active", course_id="course-1")

    async def authorized_scope(db, *, session_row, user_id):
        return binding

    monkeypatch.setattr(tutor_service, "authorize_chat_session_release_scope", authorized_scope)
    resolved = asyncio.run(
        tutor_service.authorize_selected_table_pointer(
            _PointerDb(rows),
            session_row=session_row,
            user_id="student-1",
            pointer_id=pointer.id,
        )
    )
    assert resolved.object_type == "figure"
    assert resolved.excerpt == ""


def test_selected_table_turn_is_local_extractive_and_replayable(monkeypatch) -> None:
    pointer, _, _, _ = _release_pointer_fixture()
    db = _FakeDb()
    session_row = SimpleNamespace(id="session-1", user_id="student-1")

    def forbidden_provider(*args, **kwargs):
        raise AssertionError("object-context turn must not invoke a provider")

    monkeypatch.setattr(tutor_service.knowledge_service, "hybrid_search", forbidden_provider)
    monkeypatch.setattr(tutor_service, "generate_grounded_answer", forbidden_provider)
    monkeypatch.setattr(tutor_service, "call_model", forbidden_provider)

    async def collect():
        return [
            event
            async for event in tutor_service.run_turn_stream(
                db,
                session_row=session_row,
                student_turn_id="turn-context-0001",
                client_turn_id="turn-context-0001",
                content="怎么读这张表？",
                purpose="course_qa",
                selected_evidence_pointer=pointer,
            )
        ]

    events = asyncio.run(collect())
    names = [event["event"] for event in events]
    state_index = next(
        index
        for index, event in enumerate(events)
        if event["data"].get("stage") == "explaining_object"
    )
    citation_index = names.index("citation")
    delta_index = names.index("delta")
    assert state_index < citation_index < delta_index
    assert events[state_index]["data"] == {
        "stage": "explaining_object",
        "object_type": "table",
        "evidence_pointer_id": pointer.id,
    }
    saved_student, saved_tutor = db.rows
    assert saved_student.citations == [{"evidence_pointer_id": pointer.id}]
    assert saved_tutor.citations[0]["evidence_pointer_id"] == pointer.id
    assert saved_tutor.verification["generation_provider"] == "internal_extractive"
    assert saved_tutor.verification["object_context"]["type"] == "table"
    assert "excerpt" not in saved_tutor.verification["object_context"]
    assert pointer.excerpt in saved_tutor.content

    async def replay():
        return [frame async for frame in _replay_saved_turn(saved_tutor)]

    replay_frames = asyncio.run(replay())
    replay_text = "".join(replay_frames)
    assert '"stage": "explaining_object"' in replay_text
    assert f'"evidence_pointer_id": "{pointer.id}"' in replay_text
    assert "event: citation" in replay_text
    assert "event: delta" in replay_text


def test_empty_figure_pointer_refuses_without_table_explain() -> None:
    pointer, _, _, _ = _release_pointer_fixture(object_type="figure", excerpt="")
    db = _FakeDb()
    session_row = SimpleNamespace(id="session-2", user_id="student-1")

    async def collect():
        return [
            event
            async for event in tutor_service.run_turn_stream(
                db,
                session_row=session_row,
                student_turn_id="turn-figure-0001",
                client_turn_id="turn-figure-0001",
                content="解释图像",
                purpose="course_qa",
                selected_evidence_pointer=pointer,
            )
        ]

    events = asyncio.run(collect())
    assert not any(
        event["event"] == "state" and event["data"].get("stage") == "explaining_object"
        for event in events
    )
    assert next(event["data"] for event in events if event["event"] == "done")["refusal"]
    assert db.rows[1].refusal is True
    assert "不能解释图意" in db.rows[1].content
