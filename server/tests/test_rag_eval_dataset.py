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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sample_dataset_and_run_conform_to_contract() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)

    validate_dataset(dataset)
    validate_run(dataset, run)


def test_score_run_reports_per_case_and_aggregate_metrics() -> None:
    report = score_run(_load(DATASET_PATH), _load(RUN_PATH), k=5)

    assert report["dataset_id"] == "multimodal-textbook-sample-v1"
    assert report["aggregate"]["recall_at_k"] == 1.0
    assert report["aggregate"]["bbox_iou"] == 1.0
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


def test_run_rejects_partial_case_coverage() -> None:
    dataset = _load(DATASET_PATH)
    run = _load(RUN_PATH)
    run["results"].pop()

    with pytest.raises(EvaluationDataError, match="覆盖"):
        validate_run(dataset, run)
