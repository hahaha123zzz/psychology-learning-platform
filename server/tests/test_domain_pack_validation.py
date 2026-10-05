import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.modules.courses.schemas import ReleaseCreate
from app.modules.courses.service import validate_course_release_pack


def _base_pack() -> dict:
    return {
        "knowledge_points": [
            {"key": "kp-a", "title": "A"},
            {"key": "kp-b", "title": "B"},
        ],
        "relations": [],
        "experiments": [],
        "misconceptions": [],
        "evidence_bindings": [],
    }


def _issues(
    pack: dict,
    *,
    for_publish: bool = False,
    material_ids: set[str] | None = None,
    material_versions: dict[str, str] | None = None,
    evidence_sources: dict[str, str] | None = None,
) -> list[dict]:
    with pytest.raises(ApiError) as raised:
        validate_course_release_pack(
            "domain_pack",
            pack,
            for_publish=for_publish,
            material_ids=material_ids,
            material_versions=material_versions,
            evidence_sources=evidence_sources,
        )
    assert raised.value.status_code == 422
    return raised.value.details["issues"]


def test_domain_pack_rejects_duplicate_and_noncanonical_object_keys() -> None:
    pack = _base_pack()
    pack["chapters"] = ["kp-a"]
    pack["knowledge_points"].append({"key": " kp-a ", "title": "duplicate"})
    pack["knowledge_points"].append({"key": "kp-a", "title": "duplicate exact ID"})

    issues = _issues(pack)

    codes = {issue["code"] for issue in issues}
    assert "DOMAIN_OBJECT_KEY_NOT_CANONICAL" in codes
    assert "DOMAIN_OBJECT_KEY_DUPLICATE" in codes


def test_domain_pack_rejects_dangling_self_duplicate_and_unsupported_relations() -> None:
    pack = _base_pack()
    pack["relations"] = [
        {
            "key": "r-1",
            "source_key": "kp-a",
            "target_key": "missing",
            "relation_type": "prerequisite",
        },
        {"key": "r-2", "source_key": "kp-a", "target_key": "kp-a", "relation_type": "prerequisite"},
        {"key": "r-3", "source_key": "kp-a", "target_key": "kp-b", "relation_type": "related_to"},
    ]

    issues = _issues(pack)

    codes = {issue["code"] for issue in issues}
    assert "DOMAIN_RELATION_TARGET_NOT_FOUND" in codes
    assert "DOMAIN_RELATION_SELF_REFERENCE" in codes
    assert "DOMAIN_RELATION_TYPE_UNSUPPORTED" in codes


def test_prerequisite_relation_rejects_wrong_endpoint_object_type() -> None:
    pack = _base_pack()
    pack["experiments"] = [{"key": "exp-a", "title": "实验 A"}]
    pack["relations"] = [
        {
            "key": "rel-a",
            "source_key": "exp-a",
            "target_key": "kp-a",
            "relation_type": "prerequisite",
        }
    ]

    issues = _issues(pack)

    assert any(issue["code"] == "DOMAIN_RELATION_ENDPOINT_TYPE_INVALID" for issue in issues)


def test_domain_pack_rejects_duplicate_edges_and_prerequisite_cycles() -> None:
    pack = _base_pack()
    pack["relations"] = [
        {"key": "r-1", "source_key": "kp-a", "target_key": "kp-b", "relation_type": "prerequisite"},
        {"key": "r-2", "source_key": "kp-a", "target_key": "kp-b", "relation_type": "prerequisite"},
        {"key": "r-3", "source_key": "kp-b", "target_key": "kp-a", "relation_type": "prerequisite"},
    ]

    issues = _issues(pack)

    codes = {issue["code"] for issue in issues}
    assert "DOMAIN_RELATION_DUPLICATE" in codes
    assert "DOMAIN_RELATION_CYCLE" in codes


def test_domain_pack_rejects_unknown_fields_instead_of_ignoring_them() -> None:
    pack = _base_pack()
    pack["relations"] = [
        {
            "key": "r-1",
            "source_key": "kp-a",
            "target_key": "kp-b",
            "relation_type": "prerequisite",
            "execute": "arbitrary payload",
        }
    ]

    with pytest.raises(ApiError) as raised:
        validate_course_release_pack("domain_pack", pack)

    assert raised.value.code == "RELEASE_PACK_UNKNOWN_FIELD"
    assert raised.value.details["unknown_fields"] == ["execute"]


def test_release_request_and_domain_pack_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReleaseCreate.model_validate({"name": "草稿", "domain_pakc": {}})

    with pytest.raises(ApiError) as raised:
        validate_course_release_pack("domain_pack", {"ai_candidate": [{"text": "未经审核"}]})

    assert raised.value.code == "RELEASE_PACK_UNKNOWN_FIELD"
    assert raised.value.details["field"] == "ai_candidate"


def test_experiment_and_misconception_references_must_resolve() -> None:
    pack = _base_pack()
    pack["experiments"] = [{"key": "exp-1", "title": "实验", "knowledge_point_keys": ["absent"]}]
    pack["misconceptions"] = [{"key": "mis-1", "title": "误区", "knowledge_point_keys": ["kp-b"]}]

    issues = _issues(pack)

    dangling = [issue for issue in issues if issue["code"] == "DOMAIN_KNOWLEDGE_POINT_NOT_FOUND"]
    assert len(dangling) == 1
    assert dangling[0]["key"] == "absent"


def test_experiment_schema_exposes_textbook_reasoning_fields_without_making_them_required() -> None:
    schema = ReleaseCreate.model_json_schema()["properties"]["domain_pack"]
    experiment = schema["properties"]["experiments"]["items"]
    fields = experiment["properties"]
    expected = {
        "research_question",
        "hypothesis",
        "iv",
        "dv",
        "operationalization",
        "controls",
        "confounds",
        "design",
        "procedure",
        "prediction",
        "result_pattern",
        "interpretation",
        "limitations",
        "textbook_evidence",
    }

    assert expected <= fields.keys()
    assert experiment["required"] == ["key", "title"]
    assert fields["controls"]["anyOf"][1]["maxItems"] == 50

    # 只有教材实际提供的信息才填写；未给出的字段保持省略。
    validate_course_release_pack(
        "domain_pack",
        {"experiments": [{"key": "stroop", "title": "Stroop"}]},
    )


def test_experiment_schema_accepts_documented_fields_and_rejects_invalid_shapes() -> None:
    pack = _base_pack()
    pack["experiments"] = [
        {
            "key": "stroop",
            "title": "Stroop",
            "research_question": "颜色词干扰是否减慢命名？",
            "hypothesis": "不一致条件反应更慢。",
            "iv": "词义与字体颜色的一致性",
            "dv": "颜色命名反应时",
            "operationalization": "从刺激呈现到正确按键的毫秒数",
            "controls": ["显示器刷新率"],
            "confounds": ["色觉差异"],
            "design": "被试内设计",
            "procedure": "依序完成随机化试次",
            "prediction": "不一致条件反应时更长",
            "result_pattern": "教材未给出",
            "interpretation": None,
            "limitations": "练习效应可能影响结果",
        }
    ]
    validate_course_release_pack("domain_pack", pack)

    pack["experiments"][0]["controls"] = "显示器刷新率"
    issues = _issues(pack)
    assert any(
        issue["code"] == "DOMAIN_EXPERIMENT_FIELD_INVALID"
        and issue["path"] == "experiments[0].controls"
        for issue in issues
    )


def test_experiment_schema_rejects_oversized_fields_and_arrays() -> None:
    pack = _base_pack()
    pack["experiments"] = [
        {
            "key": "stroop",
            "title": "Stroop",
            "hypothesis": "x" * 4001,
            "confounds": ["混淆"] * 51,
        }
    ]

    issues = _issues(pack)
    invalid_paths = {
        issue["path"]
        for issue in issues
        if issue["code"] == "DOMAIN_EXPERIMENT_FIELD_INVALID"
    }
    assert invalid_paths == {"experiments[0].hypothesis", "experiments[0].confounds"}


def test_experiment_textbook_evidence_alias_resolves_binding_and_rejects_conflict() -> None:
    pack = _base_pack()
    pack["experiments"] = [
        {
            "key": "exp-a",
            "title": "实验 A",
            "textbook_evidence": ["ev-exp"],
        }
    ]
    pack["evidence_bindings"] = [
        {
            "key": "ev-a",
            "object_key": "kp-a",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-a",
        },
        {
            "key": "ev-b",
            "object_key": "kp-b",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-b",
        },
        {
            "key": "ev-exp",
            "object_key": "exp-a",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-exp",
        },
    ]
    pack["knowledge_points"][0]["evidence_binding_keys"] = ["ev-a"]
    pack["knowledge_points"][1]["evidence_binding_keys"] = ["ev-b"]
    kwargs = {
        "for_publish": True,
        "material_ids": {"material-a"},
        "material_versions": {"material-a": "version-a"},
        "evidence_sources": {
            "object-a": "version-a",
            "object-b": "version-a",
            "object-exp": "version-a",
        },
    }

    validate_course_release_pack("domain_pack", pack, **kwargs)

    pack["experiments"][0]["evidence_binding_keys"] = ["different-binding"]
    issues = _issues(pack, **kwargs)
    assert any(issue["code"] == "DOMAIN_EXPERIMENT_EVIDENCE_FIELDS_CONFLICT" for issue in issues)


def test_evidence_binding_must_resolve_object_and_publish_material() -> None:
    pack = _base_pack()
    pack["evidence_bindings"] = [
        {
            "key": "ev-1",
            "object_key": "kp-a",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-a",
        }
    ]
    pack["knowledge_points"][0]["evidence_binding_keys"] = ["ev-1"]
    pack["knowledge_points"][1]["evidence_binding_keys"] = ["missing-binding"]

    issues = _issues(
        pack,
        for_publish=True,
        material_ids={"material-a"},
        material_versions={"material-a": "current-version"},
        evidence_sources={"object-a": "version-a"},
    )

    codes = {issue["code"] for issue in issues}
    assert "DOMAIN_EVIDENCE_VERSION_MISMATCH" in codes
    assert "DOMAIN_EVIDENCE_BINDING_NOT_FOUND" in codes
    assert "DOMAIN_FACT_EVIDENCE_REQUIRED" in codes


def test_evidence_binding_rejects_undeclared_domain_object() -> None:
    pack = _base_pack()
    pack["evidence_bindings"] = [
        {
            "key": "ev-1",
            "object_key": "unknown-object",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-a",
        }
    ]

    issues = _issues(pack)

    assert any(issue["code"] == "DOMAIN_EVIDENCE_OBJECT_NOT_FOUND" for issue in issues)


def test_published_evidence_must_resolve_to_source_object_in_the_bound_version() -> None:
    pack = _base_pack()
    pack["evidence_bindings"] = [
        {
            "key": "ev-a",
            "object_key": "kp-a",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "missing-source",
        },
        {
            "key": "ev-b",
            "object_key": "kp-b",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "wrong-version-source",
        },
    ]
    pack["knowledge_points"][0]["evidence_binding_keys"] = ["ev-a"]
    pack["knowledge_points"][1]["evidence_binding_keys"] = ["ev-b"]

    issues = _issues(
        pack,
        for_publish=True,
        material_ids={"material-a"},
        material_versions={"material-a": "version-a"},
        evidence_sources={"wrong-version-source": "another-version"},
    )

    codes = {issue["code"] for issue in issues}
    assert "DOMAIN_EVIDENCE_SOURCE_NOT_FOUND" in codes
    assert "DOMAIN_EVIDENCE_SOURCE_VERSION_MISMATCH" in codes
    assert "DOMAIN_FACT_EVIDENCE_REQUIRED" in codes


def test_domain_facts_without_evidence_cannot_be_published() -> None:
    pack = _base_pack()

    issues = _issues(pack, for_publish=True, material_ids=set())

    missing = [issue for issue in issues if issue["code"] == "DOMAIN_FACT_EVIDENCE_REQUIRED"]
    assert {issue["key"] for issue in missing} == {"kp-a", "kp-b"}


def test_domain_pack_with_selected_version_evidence_is_publishable() -> None:
    pack = _base_pack()
    pack["evidence_bindings"] = [
        {
            "key": "ev-a",
            "object_key": "kp-a",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-a",
        },
        {
            "key": "ev-b",
            "object_key": "kp-b",
            "material_id": "material-a",
            "material_version_id": "version-a",
            "source_object_id": "object-b",
        },
    ]
    pack["knowledge_points"][0]["evidence_binding_keys"] = ["ev-a"]
    pack["knowledge_points"][1]["evidence_binding_keys"] = ["ev-b"]

    validate_course_release_pack(
        "domain_pack",
        pack,
        for_publish=True,
        material_ids={"material-a"},
        material_versions={"material-a": "version-a"},
        evidence_sources={"object-a": "version-a", "object-b": "version-a"},
    )
