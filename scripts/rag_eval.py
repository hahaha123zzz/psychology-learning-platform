"""RAG检索基线评测：对指定课程运行问题集，输出Recall@K与稳定性报告。

用法：
  python scripts/rag_eval.py --course <course_id> [--k 8]
问题集内置（可替换为教师审核版评测集）。依赖：课程已有已解析并嵌入的资料。
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import CourseMember, User  # noqa: E402
from app.db.session import session_factory  # noqa: E402
from app.modules.knowledge import service as knowledge_service  # noqa: E402

EVAL_SET = [
    {"query": "independent variable control", "expect_page": 1},
    {"query": "between subjects participants conditions", "expect_page": 2},
    {"query": "internal validity experiments", "expect_page": 1},
    {"query": "research design assigns participants", "expect_page": 2},
    {"query": "quantum teleportation recipe", "expect_page": None},
]


async def pick_teacher(course_id: str) -> str:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(CourseMember.user_id).where(
                    CourseMember.course_id == course_id,
                    CourseMember.role == "teacher",
                    CourseMember.status == "active",
                )
            )
        ).first()
        return row[0] if row else get_settings().default_organization_id


async def run_case(course_id: str, case: dict, k: int, staff_user: str) -> dict:
    async with session_factory() as session:
        started = time.perf_counter()
        items, warnings = await knowledge_service.hybrid_search(
            session,
            user_id=staff_user,
            course_id=course_id,
            version_ids=await knowledge_service.resolve_searchable_versions(
                session,
                course_id=course_id,
                requested_version_ids=[],
                staff=True,
            ),
            query=case["query"],
            top_k=k,
            staff=True,
        )
        await session.commit()
        elapsed = time.perf_counter() - started

    expect = case["expect_page"]
    pages = [item["physical_page"] for item in items]
    hit = expect is None or (expect in pages)
    refused_appropriately = expect is None and not pages
    return {
        "query": case["query"],
        "expect_page": expect,
        "top_pages": pages[:k],
        "recall": hit or refused_appropriately,
        "refused_appropriately": refused_appropriately,
        "latency_ms": round(elapsed * 1000, 1),
        "warnings": warnings,
    }


async def main_async(course_id: str, k: int) -> None:
    staff_user = await pick_teacher(course_id)
    results = [await run_case(course_id, case, k, staff_user) for case in EVAL_SET]
    recall = sum(1 for r in results if r["recall"]) / len(results)
    report = {
        "course_id": course_id,
        "retrieval_version": knowledge_service.RETRIEVAL_VERSION,
        "k": k,
        "recall_at_k": round(recall, 3),
        "cases": results,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    target = SERVER.parent / "contracts" / "rag_eval_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", required=True)
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(main_async(args.course, args.k))
