from types import SimpleNamespace

from app.modules.knowledge.service import build_chunk_rows


def _object(**values):
    defaults = {
        "id": "object-1",
        "type": "paragraph",
        "title": None,
        "chapter_path": "1",
        "physical_page": 1,
        "reading_order": 1,
        "raw_content": "原始识别文本",
        "normalized_content": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_chunking_prefers_teacher_corrected_content() -> None:
    objects = [
        _object(
            id="chapter-1",
            type="chapter",
            title="第一章",
            raw_content="第一章",
        ),
        _object(
            id="paragraph-1",
            reading_order=2,
            normalized_content="教师修正后的文本",
        ),
    ]

    rows = build_chunk_rows(objects)

    assert len(rows) == 1
    assert rows[0]["text"] == "第一章\n教师修正后的文本"
    assert "原始识别文本" not in rows[0]["text"]
