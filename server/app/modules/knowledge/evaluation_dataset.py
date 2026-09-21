"""RAG V3 评测数据集与运行结果的离线校验、评分。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.modules.knowledge.evaluation import (
    bbox_iou,
    citation_precision_recall,
    claim_support_rate,
    ndcg_at_k,
    page_accuracy,
    recall_at_k,
    refusal_accuracy,
)


class EvaluationDataError(ValueError):
    """评测数据不满足 V3 合同时抛出。"""


def validate_dataset(dataset: Mapping[str, Any]) -> None:
    _require(dataset, "dataset_id", str)
    if dataset.get("schema_version") != "rag-eval/v3":
        raise EvaluationDataError("schema_version 必须为 rag-eval/v3")
    documents = _require_list(dataset, "documents")
    objects = _require_list(dataset, "objects")
    cases = _require_list(dataset, "cases")
    document_ids = _unique_ids(documents, "documents")
    object_ids = _unique_ids(objects, "objects")
    _unique_ids(cases, "cases")

    for item in objects:
        _require(item, "document_id", str)
        if item["document_id"] not in document_ids:
            raise EvaluationDataError(f"对象引用了未知文档: {item['document_id']}")
        _require(item, "object_type", str)
        page = _require(item, "page", int)
        if page < 1:
            raise EvaluationDataError("对象 page 必须从 1 开始")
        bbox = _number_list(item, "bbox")
        if len(bbox) != 4 or bbox_iou(bbox, bbox) != 1.0:
            raise EvaluationDataError(f"对象 bbox 非法: {item['id']}")

    for case in cases:
        _require(case, "query", str)
        _require(case, "expected_refusal", bool)
        relevant = _string_list(case, "relevant_object_ids")
        allowed = _string_list(case, "allowed_evidence_ids")
        unknown = (set(relevant) | set(allowed)) - object_ids
        if unknown:
            raise EvaluationDataError(f"问题引用了未知对象: {sorted(unknown)}")
        if case["expected_refusal"] and (relevant or allowed):
            raise EvaluationDataError("拒答问题不能包含相关对象或允许引用")
        if not case["expected_refusal"] and not relevant:
            raise EvaluationDataError("可回答问题至少需要一个相关对象")
        if not set(allowed).issubset(relevant):
            raise EvaluationDataError("allowed_evidence_ids 必须是 relevant_object_ids 的子集")


def validate_run(dataset: Mapping[str, Any], run: Mapping[str, Any]) -> None:
    validate_dataset(dataset)
    if run.get("schema_version") != "rag-eval/v3-run":
        raise EvaluationDataError("运行结果 schema_version 必须为 rag-eval/v3-run")
    if run.get("dataset_id") != dataset["dataset_id"]:
        raise EvaluationDataError("运行结果 dataset_id 与评测集不一致")
    results = _require_list(run, "results")
    expected_cases = {case["id"] for case in dataset["cases"]}
    received_cases = _unique_ids(results, "results", id_key="case_id")
    if received_cases != expected_cases:
        raise EvaluationDataError("运行结果必须覆盖且仅覆盖评测集中的全部问题")

    object_ids = {item["id"] for item in dataset["objects"]}
    for result in results:
        for key in ("retrieved_object_ids", "cited_object_ids", "claim_support_levels"):
            _string_list(result, key)
        unknown = (
            set(result["retrieved_object_ids"]) | set(result["cited_object_ids"])
        ) - object_ids
        if unknown:
            raise EvaluationDataError(f"运行结果引用了未知对象: {sorted(unknown)}")
        _require(result, "refused", bool)
        if result.get("predicted_page") is not None and (
            not isinstance(result["predicted_page"], int) or result["predicted_page"] < 1
        ):
            raise EvaluationDataError("predicted_page 必须为正整数或 null")
        bbox = result.get("predicted_bbox")
        if bbox is not None and (not isinstance(bbox, list) or bbox_iou(bbox, bbox) != 1.0):
            raise EvaluationDataError("predicted_bbox 非法")


def score_run(dataset: Mapping[str, Any], run: Mapping[str, Any], *, k: int = 5) -> dict[str, Any]:
    """对已校验运行结果输出逐题和聚合评测指标。"""

    validate_run(dataset, run)
    cases = {case["id"]: case for case in dataset["cases"]}
    objects = {item["id"]: item for item in dataset["objects"]}
    per_case: list[dict[str, Any]] = []
    refusal_predictions: list[bool] = []
    refusal_expected: list[bool] = []

    for result in run["results"]:
        case = cases[result["case_id"]]
        relevant = case["relevant_object_ids"]
        allowed = case["allowed_evidence_ids"]
        expected_pages = {objects[object_id]["page"] for object_id in relevant}
        expected_boxes = [objects[object_id]["bbox"] for object_id in relevant]
        citation_precision, citation_recall = citation_precision_recall(
            result["cited_object_ids"], allowed
        )
        bbox_score = max(
            (bbox_iou(result.get("predicted_bbox"), bbox) for bbox in expected_boxes), default=0.0
        )
        metrics = {
            "case_id": case["id"],
            "recall_at_k": recall_at_k(result["retrieved_object_ids"], relevant, k),
            "ndcg_at_k": ndcg_at_k(result["retrieved_object_ids"], relevant, k),
            "page_accuracy": page_accuracy(result.get("predicted_page"), expected_pages),
            "bbox_iou": bbox_score,
            "citation_precision": citation_precision,
            "citation_recall": citation_recall,
            "claim_support_rate": claim_support_rate(result["claim_support_levels"]),
            "refused": result["refused"],
            "expected_refusal": case["expected_refusal"],
            "latency_ms": result.get("latency_ms"),
        }
        per_case.append(metrics)
        refusal_predictions.append(result["refused"])
        refusal_expected.append(case["expected_refusal"])

    answerable_cases = [item for item in per_case if not item["expected_refusal"]]
    numeric_keys = (
        "recall_at_k",
        "ndcg_at_k",
        "page_accuracy",
        "bbox_iou",
        "citation_precision",
        "citation_recall",
        "claim_support_rate",
    )
    aggregate = {
        key: round(sum(item[key] for item in answerable_cases) / len(answerable_cases), 6)
        if answerable_cases
        else None
        for key in numeric_keys
    }
    aggregate["answerable_case_count"] = len(answerable_cases)
    aggregate["refusal_accuracy"] = round(
        refusal_accuracy(refusal_predictions, refusal_expected), 6
    )
    latencies = [item["latency_ms"] for item in per_case if isinstance(item["latency_ms"], float)]
    aggregate["mean_latency_ms"] = round(sum(latencies) / len(latencies), 3) if latencies else None
    return {"dataset_id": dataset["dataset_id"], "k": k, "aggregate": aggregate, "cases": per_case}


def _require(mapping: Mapping[str, Any], key: str, expected_type: type) -> Any:
    value = mapping.get(key)
    if not isinstance(value, expected_type) or (expected_type is str and not value.strip()):
        raise EvaluationDataError(f"{key} 必须为有效 {expected_type.__name__}")
    return value


def _require_list(mapping: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise EvaluationDataError(f"{key} 必须为非空列表")
    if not all(isinstance(item, dict) for item in value):
        raise EvaluationDataError(f"{key} 每项必须为对象")
    return value


def _string_list(mapping: Mapping[str, Any], key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise EvaluationDataError(f"{key} 必须为字符串列表")
    return value


def _number_list(mapping: Mapping[str, Any], key: str) -> list[float]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
    ):
        raise EvaluationDataError(f"{key} 必须为数值列表")
    return [float(item) for item in value]


def _unique_ids(
    items: list[dict[str, Any]], label: str, *, id_key: str = "id"
) -> set[str]:
    ids: list[str] = []
    for item in items:
        value = _require(item, id_key, str)
        ids.append(value)
    if len(ids) != len(set(ids)):
        raise EvaluationDataError(f"{label} 存在重复 {id_key}")
    return set(ids)
