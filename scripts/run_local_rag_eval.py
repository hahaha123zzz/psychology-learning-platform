"""以本地 hash-v1 索引运行 V3 教材检索评测，不向外部服务发送教材内容。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

from app.core.embedding import get_embedding_client
from app.db.models import Material, MaterialVersion
from app.db.session import session_factory
from app.modules.knowledge import service as knowledge_service
from app.modules.knowledge.query import analyze_query


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_object_id(item: dict, objects: list[dict]) -> str:
    """仅以标注的同页文本锚点替换真实对象 ID，未命中时保留真实 ID。"""
    text = item["text"].lower()
    for annotated in objects:
        anchor = annotated.get("text_anchor", "").lower()
        if (
            annotated["page"] == item["physical_page"]
            and annotated["object_type"] == item["object_type"]
            and anchor
            and anchor in text
        ):
            return annotated["id"]
    return item["source_object_id"]


async def _run(dataset: dict, version_id: str, top_k: int) -> dict:
    client = get_embedding_client()
    if client.version != "hash-v1":
        raise RuntimeError(
            "本地开放教材评测只允许 hash-v1；请移除外部 Embedding 配置后重试"
        )
    document = dataset["documents"][0]
    async with session_factory() as db:
        version = await db.get(MaterialVersion, version_id)
        if version is None:
            raise RuntimeError(f"找不到教材版本: {version_id}")
        if version.status != "parsed":
            raise RuntimeError(f"教材版本尚不可检索: {version.status}")
        if version.sha256 != document.get("sha256"):
            raise RuntimeError("教材版本 SHA-256 与评测集文档不一致")
        material = await db.get(Material, version.material_id)
        if material is None:
            raise RuntimeError("教材版本缺少所属资料")

        results: list[dict] = []
        for case in dataset["cases"]:
            plan = analyze_query(case["query"])
            started = time.perf_counter()
            items, _warnings = await knowledge_service.hybrid_search(
                db,
                user_id=version.created_by,
                course_id=material.course_id,
                version_ids=[version.id],
                query=case["query"],
                top_k=min(top_k, plan.retrieval_budget),
                staff=True,
                include_neighbors=False,
                channel_priors=plan.channel_priors,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            results.append(
                {
                    "case_id": case["id"],
                    "retrieved_object_ids": [
                        _canonical_object_id(item, dataset["objects"]) for item in items
                    ],
                    "retrieved_pages": [item["physical_page"] for item in items],
                    "predicted_page": items[0]["physical_page"] if items else None,
                    "predicted_bbox": items[0]["bbox"] if items else None,
                    "cited_object_ids": [],
                    "claim_support_levels": [],
                    "generation_evaluated": False,
                    "object_mapping_evaluated": all(
                        annotated["object_type"] == "paragraph"
                        for annotated in dataset["objects"]
                        if annotated["id"] in case["relevant_object_ids"]
                    ),
                    "refused": not items,
                    "latency_ms": latency_ms,
                }
            )
        await db.rollback()  # EvidenceTicket 仅用于在线会话，离线评测不持久化。
    return {
        "dataset_id": dataset["dataset_id"],
        "schema_version": "rag-eval/v3-run",
        "run_id": f"{dataset['dataset_id']}-local-{knowledge_service.RETRIEVAL_VERSION}-{client.version}",
        "retrieval_version": knowledge_service.RETRIEVAL_VERSION,
        "embedding_version": client.version,
        "material_version_id": version_id,
        "matching_note": "本地 hash-v1 自动运行；同页 text_anchor 命中时映射评测对象，否则保留真实来源对象 ID。",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行本地离线教材 RAG V3 评测")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--material-version-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    if args.top_k < 1:
        raise SystemExit("--top-k 必须大于 0")
    try:
        run = asyncio.run(_run(_read_json(args.dataset), args.material_version_id, args.top_k))
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"离线评测失败: {exc}") from exc
    args.output.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
