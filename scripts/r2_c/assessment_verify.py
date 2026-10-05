"""以数据库只读状态核验 R2-C 测评自动保存/封存结果，不输出作答正文。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

from runtime_guard import validate_e2e_environment  # noqa: E402

from app.db.models import Attempt, AttemptAnswer, LearningEvent, ScoreRecord  # noqa: E402
from app.db.session import session_factory  # noqa: E402


async def main() -> None:
    validate_e2e_environment()
    attempt_id = os.environ.get("R2_C_ATTEMPT_ID", "")
    if not attempt_id:
        raise RuntimeError("必须指定 R2_C_ATTEMPT_ID")
    async with session_factory() as db:
        attempt = await db.get(Attempt, attempt_id)
        if attempt is None:
            raise RuntimeError("R2-C 专属测评尝试不存在")
        answer_count = await db.scalar(
            select(func.count()).select_from(AttemptAnswer).where(
                AttemptAnswer.attempt_id == attempt_id
            )
        )
        score_count = await db.scalar(
            select(func.count()).select_from(ScoreRecord).where(
                ScoreRecord.attempt_id == attempt_id
            )
        )
        event_count = await db.scalar(
            select(func.count()).select_from(LearningEvent).where(
                LearningEvent.source_type == "assessment",
                LearningEvent.source_ref == attempt_id,
                LearningEvent.event_type == "answer_submitted",
            )
        )
        print(
            json.dumps(
                {
                    "status": attempt.status,
                    "answer_rows": int(answer_count or 0),
                    "score_rows": int(score_count or 0),
                    "submitted_events": int(event_count or 0),
                    "answer_text_logged": False,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
