from sqlalchemy import CheckConstraint, UniqueConstraint

from app.db.base import Base


def _constraint_names(table_name: str, constraint_type: type) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def test_rag_v3_tables_are_registered_in_metadata() -> None:
    expected = {
        "object_assets",
        "object_representations",
        "object_relations",
        "retrieval_units",
        "retrieval_index_entries",
        "parse_review_issues",
    }

    assert expected.issubset(Base.metadata.tables)


def test_material_version_has_immutable_render_and_quality_gate_fields() -> None:
    columns = Base.metadata.tables["material_versions"].columns

    assert {
        "canonical_pdf_key",
        "render_manifest",
        "render_version",
        "pipeline_version",
        "quality_gate_status",
    }.issubset(columns.keys())
    assert "ck_material_versions_quality_gate" in _constraint_names(
        "material_versions", CheckConstraint
    )


def test_retrieval_units_separate_source_parent_and_representation() -> None:
    columns = Base.metadata.tables["retrieval_units"].columns

    assert {
        "material_version_id",
        "source_object_id",
        "parent_object_id",
        "representation_id",
        "unit_type",
        "channel_hint",
        "content_hash",
        "build_strategy",
        "build_version",
    }.issubset(columns.keys())
    assert {
        "ck_retrieval_units_type",
        "ck_retrieval_units_channel",
        "ck_retrieval_units_status",
    }.issubset(_constraint_names("retrieval_units", CheckConstraint))
    assert "uq_retrieval_units_build" in _constraint_names("retrieval_units", UniqueConstraint)


def test_index_and_review_tables_have_versioned_state_contracts() -> None:
    index_columns = Base.metadata.tables["retrieval_index_entries"].columns
    review_columns = Base.metadata.tables["parse_review_issues"].columns

    assert {"channel", "provider", "model", "model_version", "index_version", "status"}.issubset(
        index_columns.keys()
    )
    assert {"severity", "code", "status", "resolution", "resolved_by"}.issubset(
        review_columns.keys()
    )
    assert "ck_retrieval_index_entries_status" in _constraint_names(
        "retrieval_index_entries", CheckConstraint
    )
    assert "ck_parse_review_issues_severity" in _constraint_names(
        "parse_review_issues", CheckConstraint
    )
