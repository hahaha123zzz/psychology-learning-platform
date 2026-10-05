"""扫描并重派发心跳超时的教材解析/索引任务。

用法（仓库根）：
    server\\.venv\\Scripts\\python.exe scripts/requeue_stale_jobs.py [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from app.core.job_recovery import find_stale_jobs, requeue_stale_jobs
from app.db.session import session_factory


async def main() -> int:
    parser = argparse.ArgumentParser(description="重派发心跳超时的教材任务")
    parser.add_argument("--dry-run", action="store_true", help="只列出陈旧任务，不重派发")
    args = parser.parse_args()

    async with session_factory() as db:
        if args.dry_run:
            from datetime import UTC, datetime, timedelta

            from app.core.config import get_settings

            threshold = datetime.now(UTC) - timedelta(seconds=get_settings().task_stale_seconds)
            stale = await find_stale_jobs(db, older_than=threshold)
            for job in stale:
                print(f"{job.id} kind={job.kind} heartbeat={job.last_heartbeat_at}")
            print(f"共 {len(stale)} 个陈旧任务")
            return 0
        recovered = await requeue_stale_jobs(db)
        for job_id in recovered:
            print(f"已重新派发 {job_id}")
        print(f"共恢复 {len(recovered)} 个任务")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
