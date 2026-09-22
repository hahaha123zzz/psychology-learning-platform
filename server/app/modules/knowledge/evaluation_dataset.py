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
        bbox = item.get("bbox")
        if bbox is not None:
            normalized_bbox = _number_list(item, "bbox")
            if len(normalized_bbox) != 4 or bbox_iou(normalized_bbox, normalized_bbox) != 1.0:
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

    for result in results:
        for key in ("retrieved_object_ids", "cited_object_ids", "claim_support_levels"):
            _string_list(result, key)
        # 保留全部候选的真实/不透明 ID，避免删除未标注结果后压缩相关对象名次，
        # 从而虚高 Recall/NDCG。相关对象仍只由数据集中的标注定义。
        retrieved_pages = result.get("retrieved_pages")
        if retrieved_pages is not None and (
            not isinstance(retrieved_pages, list)
            or not all(
                isinstance(page, int) and not isinstance(page, bool) and page >= 1
                for page in retrieved_pages
            )
        ):
            raise EvaluationDataError("retrieved_pages 必须为正整数列表")
        generation_evaluated = result.get("generation_evaluated", True)
        if not isinstance(generation_evaluated, bool):
            raise EvaluationDataError("generation_evaluated 必须为布尔值")
        if not generation_evaluated and (
            result["cited_object_ids"] or result["claim_support_levels"]
        ):
            raise EvaluationDataError("未评测生成时不得填写引用或主张支持结果")
        if not isinstance(result.get("object_mapping_evaluated", True), bool):
            raise EvaluationDataError("object_mapping_evaluated 必须为布尔值")
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
        expected_boxes = [
            objects[object_id].get("bbox")
            for object_id in relevant
            if objects[object_id].get("bbox") is not None
        ]
        generation_evaluated = result.get("generation_evaluated", True)
        object_mapping_evaluated = result.get("object_mapping_evaluated", True)
        citation_precision, citation_recall = (
            citation_precision_recall(result["cited_object_ids"], allowed)
            if generation_evaluated
            else (None, None)
        )
        retrieved_pages = result.get("retrieved_pages")
        if retrieved_pages is None:
            predicted_page = result.get("predicted_page")
            retrieved_pages = [predicted_page] if predicted_page is not None else []
        bbox_score = (
            max(bbox_iou(result.get("predicted_bbox"), bbox) for bbox in expected_boxes)
            if expected_boxes
            else None
        )
        answerable = not case["expected_refusal"]
        metrics = {
            "case_id": case["id"],
            "recall_at_k": (
                recall_at_k(result["retrieved_object_ids"], relevant, k)
                if answerable and object_mapping_evaluated
                else None
            ),
            "ndcg_at_k": (
                ndcg_at_k(result["retrieved_object_ids"], relevant, k)
                if answerable and object_mapping_evaluated
                else None
            ),
            "object_mapping_evaluated": object_mapping_evaluated,
            "page_recall_at_k": (
                recall_at_k(retrieved_pages, expected_pages, k) if answerable else None
            ),
            "page_ndcg_at_k": (
                ndcg_at_k(retrieved_pages, expected_pages, k) if answerable else None
            ),
            "page_accuracy": (
                page_accuracy(result.get("predicted_page"), expected_pages)
                if answerable
                else None
            ),
            "bbox_iou": bbox_score,
            "citation_precision": citation_precision,
            "citation_recall": citation_recall,
            "claim_support_rate": (
                claim_support_rate(result["claim_support_levels"])
                if generation_evaluated
                else None
            ),
            "generation_evaluated": generation_evaluated,
            "refused": result["refused"],
            "expected_refusal": case["expected_refusal"],
            "latency_ms": result.get("latency_ms"),
        }
        per_case.append(metrics)
        refusal_predictions.append(result["refused"])
        refusal_expected.append(case["expected_refusal"])

    answerable_cases = [item for item in per_case if not item["expected_refusal"]]
    retrieval_numeric_keys = ("page_recall_at_k", "page_ndcg_at_k", "page_accuracy")
    aggregate = {
        key: round(sum(item[key] for item in answerable_cases) / len(answerable_cases), 6)
        if answerable_cases
        else None
        for key in retrieval_numeric_keys
    }
    object_mapping_cases = [
        item for item in answerable_cases if item["object_mapping_evaluated"]
    ]
    for key in ("recall_at_k", "ndcg_at_k"):
        aggregate[key] = (
            round(
                sum(item[key] for item in object_mapping_cases)
                / len(object_mapping_cases),
                6,
            )
            if object_mapping_cases
            else None
        )
    aggregate["object_mapping_evaluable_case_count"] = len(object_mapping_cases)
    aggregate["object_mapping_unavailable_case_count"] = (
        len(answerable_cases) - len(object_mapping_cases)
    )
    generation_cases = [item for item in answerable_cases if item["generation_evaluated"]]
    for key in ("citation_precision", "citation_recall", "claim_support_rate"):
        aggregate[key] = (
            round(sum(item[key] for item in generation_cases) / len(generation_cases), 6)
            if generation_cases
            else None
        )
    aggregate["generation_evaluable_case_count"] = len(generation_cases)
    aggregate["generation_unavailable_case_count"] = (
        len(answerable_cases) - len(generation_cases)
    )
    bbox_cases = [item for item in answerable_cases if item["bbox_iou"] is not None]
    aggregate["bbox_iou"] = (
        round(sum(item["bbox_iou"] for item in bbox_cases) / len(bbox_cases), 6)
        if bbox_cases
        else None
    )
    aggregate["bbox_evaluable_case_count"] = len(bbox_cases)
    aggregate["bbox_unavailable_case_count"] = len(answerable_cases) - len(bbox_cases)
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
