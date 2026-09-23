from app.modules.knowledge.context import assemble_generation_units


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
