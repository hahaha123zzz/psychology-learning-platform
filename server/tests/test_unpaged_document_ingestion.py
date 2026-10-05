import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import (
    Course,
    Job,
    KnowledgeObject,
    Material,
    MaterialVersion,
    ParsedPage,
    User,
)
from app.db.session import session_factory
from app.modules.knowledge.service import build_chunk_rows
from app.modules.materials.parsers.base import ParsedObject, ParserResult
from app.modules.materials.service import run_parse_job
from app.modules.question_agent.service import generate_candidates
from tests.conftest import create_user_sync


class _UnpagedParser:
    name = "unpaged-test"
    version = "1.0"

    def parse(self, _data: bytes, _content_type: str) -> ParserResult:
        return ParserResult(
            page_count=None,
            objects=[
                ParsedObject(
                    type="chapter",
                    title="第一章",
                    raw_content="第一章",
                    physical_page=None,
                    reading_order=1,
                ),
                ParsedObject(
                    type="paragraph",
                    raw_content="没有固定版面依据的段落。",
                    physical_page=None,
                    reading_order=2,
                ),
            ],
            issues=["layout_bbox_unavailable"],
        )


def test_unpaged_document_is_persisted_without_inventing_a_physical_page(
    client, monkeypatch
) -> None:
    user_id = create_user_sync(email="unpaged-docx-owner@uni.edu")

    async def _create_parse_job() -> tuple[str, str]:
        async with session_factory() as session:
            user = await session.get(User, user_id)
            assert user is not None
            course = Course(
                organization_id=get_settings().default_organization_id,
                title="无固定版面测试课程",
                term="2026 秋",
                created_by=user_id,
            )
            session.add(course)
            await session.flush()
            material = Material(
                course_id=course.id,
                title="无固定版面 DOCX",
                material_type="textbook",
                created_by=user_id,
            )
            session.add(material)
            await session.flush()
            version = MaterialVersion(
                material_id=material.id,
                version_no=1,
                status="uploaded",
                object_key="fixture/unpaged.docx",
                content_type=(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                original_filename="unpaged.docx",
                created_by=user_id,
            )
            session.add(version)
            await session.flush()
            job = Job(
                kind="material_parse",
                status="queued",
                payload={"material_version_id": version.id},
                created_by=user_id,
            )
            session.add(job)
            await session.commit()
            return job.id, version.id

    job_id, version_id = asyncio.run(_create_parse_job())

    async def _get_fixture_bytes(_object_key: str) -> bytes:
        return b"test document bytes"

    monkeypatch.setattr("app.core.storage.get_object_bytes", _get_fixture_bytes)
    monkeypatch.setattr(
        "app.modules.materials.parsers.base.get_parser", lambda _content_type: _UnpagedParser()
    )

    asyncio.run(run_parse_job(job_id, version_id))

    async def _read_results() -> tuple[list[int | None], int | None, int, str]:
        async with session_factory() as session:
            objects = list(
                (
                    await session.execute(
                        select(KnowledgeObject)
                        .where(KnowledgeObject.material_version_id == version_id)
                        .order_by(KnowledgeObject.reading_order)
                    )
                ).scalars()
            )
            version = await session.get(MaterialVersion, version_id)
            job = await session.get(Job, job_id)
            parsed_page_count = len(
                list(
                    (
                        await session.execute(
                            select(ParsedPage).where(ParsedPage.material_version_id == version_id)
                        )
                    ).scalars()
                )
            )
            assert version is not None and job is not None
            return (
                [item.physical_page for item in objects],
                version.page_count,
                parsed_page_count,
                job.status,
            )

    physical_pages, page_count, parsed_page_count, job_status = asyncio.run(_read_results())
    assert physical_pages == [None, None]
    assert page_count is None
    assert parsed_page_count == 0
    assert job_status == "succeeded"

    chunks = build_chunk_rows(
        [
            KnowledgeObject(
                id="01J9UNPAGEDCHUNKOBJECT000000",
                material_version_id=version_id,
                type="paragraph",
                chapter_path="1",
                physical_page=None,
                reading_order=2,
                raw_content="没有固定版面依据的段落。",
                parser="unpaged-test",
                parser_version="1.0",
            )
        ]
    )
    assert len(chunks) == 1
    assert chunks[0]["physical_page"] is None


def test_question_candidate_does_not_invent_a_page_when_evidence_is_unpaged() -> None:
    candidates = generate_candidates(
        [
            {
                "chunk_id": "chunk-1",
                "material_title": "本地 DOCX 教材",
                "page": None,
                "text": "一个足够长的第一条教材事实描述，用来验证无页码的情况。",
            },
            {
                "chunk_id": "chunk-2",
                "material_title": "本地 DOCX 教材",
                "page": None,
                "text": "另一个足够长的第二条教材事实描述，用作不同的错误选项。",
            },
            {
                "chunk_id": "chunk-3",
                "material_title": "本地 DOCX 教材",
                "page": None,
                "text": "还有一条足够长的第三条教材事实描述，作为第二个错误选项。",
            },
        ],
        count=1,
        difficulty_distribution=None,
    )

    assert len(candidates) == 1
    assert "None" not in candidates[0]["stem"]
    assert "第" not in candidates[0]["stem"]
    assert "None" not in candidates[0]["explanation"]

