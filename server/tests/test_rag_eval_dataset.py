import json
from pathlib import Path

import pytest

from app.modules.knowledge.evaluation_dataset import (
    EvaluationDataError,
    score_run,
    validate_dataset,
    validate_run,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "contracts" / "rag-eval" / "v3-sample.json"
RUN_PATH = ROOT / "contracts" / "rag-eval" / "v3-run-sample.json"
OPENSTAX_DATASET_PATH = ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-v1.json"
OPENSTAX_RUN_PATH = (
    ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-hybrid-v1-run.json"
)
OPENSTAX_V2_DATASET_PATH = ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-v2.json"
OPENSTAX_V2_RUN_PATH = (
    ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-hybrid-v2-run.json"
)
OPENSTAX_V3_RUN_PATH = (
    ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-hybrid-v3-run.json"
)
OPENSTAX_V3_REPORT_PATH = (
    ROOT / "contracts" / "rag-eval" / "openstax-psychology-2e-local-hybrid-v3-report.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sample_dataset_and_run_conform_to_contract() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)

    validate_dataset(dataset)
    validate_run(dataset, run)


def test_openstax_local_dataset_conforms_without_fabricated_bboxes() -> None:
    dataset = _load(OPENSTAX_DATASET_PATH)

    validate_dataset(dataset)
    assert dataset["documents"][0]["page_count"] == 755
    assert all("bbox" not in item for item in dataset["objects"])


def test_openstax_local_retrieval_baseline_is_reproducibly_scored() -> None:
    dataset = _load(OPENSTAX_DATASET_PATH)
    run = _load(OPENSTAX_RUN_PATH)

    validate_run(dataset, run)
    report = score_run(dataset, run, k=5)

    assert report["aggregate"]["page_recall_at_k"] == 1.0
    assert report["aggregate"]["page_ndcg_at_k"] == 0.926186
    assert report["aggregate"]["page_accuracy"] == 0.8
    assert report["aggregate"]["refusal_accuracy"] == 0.833333
    assert report["aggregate"]["bbox_iou"] is None


def test_openstax_v2_object_mapping_and_refusal_baseline_is_reproducibly_scored() -> None:
    dataset = _load(OPENSTAX_V2_DATASET_PATH)
    run = _load(OPENSTAX_V2_RUN_PATH)

    validate_run(dataset, run)
    report = score_run(dataset, run, k=5)

    assert report["aggregate"]["recall_at_k"] == 0.875
    assert report["aggregate"]["ndcg_at_k"] == 0.718752
    assert report["aggregate"]["refusal_accuracy"] == 1.0
    assert report["aggregate"]["object_mapping_evaluable_case_count"] == 4
    assert report["cases"][2]["recall_at_k"] is None


def test_openstax_v3_automated_local_baseline_is_reproducibly_scored() -> None:
    dataset = _load(OPENSTAX_V2_DATASET_PATH)
    run = _load(OPENSTAX_V3_RUN_PATH)
    saved_report = _load(OPENSTAX_V3_REPORT_PATH)

    validate_run(dataset, run)
    report = score_run(dataset, run, k=5)

    assert run["retrieval_version"] == "hybrid-v3"
    assert run["embedding_version"] == "hash-v1"
    assert report == saved_report
    assert report["aggregate"]["page_recall_at_k"] == 1.0
    assert report["aggregate"]["recall_at_k"] == 0.625
    assert report["aggregate"]["ndcg_at_k"] == 0.561019
    assert report["aggregate"]["refusal_accuracy"] == 1.0
    assert report["aggregate"]["object_mapping_unavailable_case_count"] == 1


def test_score_run_reports_per_case_and_aggregate_metrics() -> None:
    report = score_run(_load(DATASET_PATH), _load(RUN_PATH), k=5)

    assert report["dataset_id"] == "multimodal-textbook-sample-v1"
    assert report["aggregate"]["recall_at_k"] == 1.0
    assert report["aggregate"]["bbox_iou"] == 1.0
    assert report["aggregate"]["bbox_evaluable_case_count"] == 2
    assert report["aggregate"]["bbox_unavailable_case_count"] == 0
    assert report["aggregate"]["answerable_case_count"] == 2
    assert report["aggregate"]["refusal_accuracy"] == 1.0
    assert len(report["cases"]) == 3


def test_dataset_rejects_unknown_object_reference() -> None:
    dataset = _load(DATASET_PATH)
    dataset["cases"][0]["relevant_object_ids"] = ["missing"]

    with pytest.raises(EvaluationDataError, match="未知对象"):
        validate_dataset(dataset)


def test_dataset_rejects_answerable_case_without_evidence() -> None:
    dataset = _load(DATASET_PATH)
    dataset["cases"][0]["relevant_object_ids"] = []

    with pytest.raises(EvaluationDataError, match="至少需要一个相关对象"):
        validate_dataset(dataset)


def test_missing_bbox_is_honestly_excluded_from_bbox_metric() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    for item in dataset["objects"]:
        item.pop("bbox")

    validate_dataset(dataset)
    report = score_run(dataset, run, k=5)

    assert report["cases"][0]["bbox_iou"] is None
    assert report["aggregate"]["bbox_iou"] is None
    assert report["aggregate"]["bbox_evaluable_case_count"] == 0
    assert report["aggregate"]["bbox_unavailable_case_count"] == 2


def test_run_rejects_partial_case_coverage() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    run["results"].pop()

    with pytest.raises(EvaluationDataError, match="覆盖"):
        validate_run(dataset, run)


def test_run_preserves_unannotated_results_in_rank_and_scores_pages() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    first = run["results"][0]
    first["retrieved_object_ids"] = ["opaque-unannotated", "obj-figure-stroop"]
    first["retrieved_pages"] = [99, 1]

    validate_run(dataset, run)
    report = score_run(dataset, run, k=5)

    assert report["cases"][0]["ndcg_at_k"] < 1.0
    assert report["cases"][0]["page_ndcg_at_k"] < 1.0
    assert report["cases"][0]["page_recall_at_k"] == 1.0


def test_retrieval_only_run_excludes_generation_metrics() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    for result in run["results"]:
        result["generation_evaluated"] = False
        result["cited_object_ids"] = []
        result["claim_support_levels"] = []

    report = score_run(dataset, run, k=5)

    assert report["aggregate"]["citation_precision"] is None
    assert report["aggregate"]["claim_support_rate"] is None
    assert report["aggregate"]["generation_evaluable_case_count"] == 0
    assert report["aggregate"]["generation_unavailable_case_count"] == 2


def test_run_excludes_exact_object_metrics_without_stable_mapping() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    for result in run["results"]:
        result["object_mapping_evaluated"] = False

    report = score_run(dataset, run, k=5)

    assert report["aggregate"]["recall_at_k"] is None
    assert report["aggregate"]["ndcg_at_k"] is None
    assert report["aggregate"]["object_mapping_evaluable_case_count"] == 0
    assert report["aggregate"]["object_mapping_unavailable_case_count"] == 2
    assert report["cases"][-1]["page_recall_at_k"] is None
