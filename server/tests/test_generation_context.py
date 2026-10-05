from app.modules.knowledge.context import assemble_generation_units
from app.modules.tutor.service import build_evidence_package


def _item(object_id: str, text: str, closure: list[dict] | None = None) -> dict:
    return {
        "evidence_id": f"ev-{object_id}",
        "source_object_id": object_id,
        "material_version_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "object_type": "paragraph",
        "physical_page": 1,
        "bbox": [0, 0, 1, 1],
        "text": text,
        "closure": closure or [],
    }


def test_generation_units_include_closure_and_deduplicate_coverage() -> None:
    units = assemble_generation_units(
        [
            _item("a", "primary", [{"object_id": "b", "text": "neighbor"}]),
            _item("b", "duplicate neighbor"),
        ],
        context_budget_chars=100,
    )

    assert len(units) == 1
    assert units[0].text == "primary\nneighbor"
    assert [obj["role"] for obj in units[0].objects] == ["primary", "closure"]


def test_generation_units_respect_budget() -> None:
    units = assemble_generation_units([_item("a", "abcdefghij")], context_budget_chars=4)

    assert units[0].text == "abcd"


def test_generation_units_exclude_table_and_figure_content() -> None:
    paragraph = _item(
        "paragraph-1",
        "正文证据",
        [
            {"object_id": "table-1", "object_type": "table", "text": "表格单元格"},
            {"object_id": "figure-1", "object_type": "figure", "text": "图像描述"},
        ],
    )
    table = _item("table-2", "另一张表格")
    table["object_type"] = "table"

    units = assemble_generation_units([paragraph, table], context_budget_chars=100)

    assert len(units) == 1
    assert units[0].text == "正文证据"
    assert [obj["object_id"] for obj in units[0].objects] == ["paragraph-1"]


def test_tutor_evidence_package_strips_table_and_figure_closure_metadata() -> None:
    paragraph = _item(
        "paragraph-1",
        "正文证据",
        [
            {"object_id": "table-1", "object_type": "table", "text": "表格", "bbox": [1, 2]},
            {
                "object_id": "figure-1",
                "object_type": "figure",
                "text": "图像",
                "evidence_pointer_id": "pointer-1",
            },
            {"object_id": "paragraph-2", "text": "相邻正文"},
        ],
    )

    package = build_evidence_package(
        user_id="student-1",
        course_id="course-1",
        query="正文",
        items=[paragraph],
    )

    assert package.items[0]["closure"] == [{"object_id": "paragraph-2", "text": "相邻正文"}]
    assert "table-1" not in repr(package.items)
    assert "figure-1" not in repr(package.items)
