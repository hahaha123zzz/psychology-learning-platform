"""领取并资格化待处理学习事件。

用法（仓库根）：
    server\\.venv\\Scripts\\python.exe scripts/qualify_learning_events.py --limit 100
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from app.db.session import session_factory
from app.modules.learning_events.qualification import (
    qualify_pending_events,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="资格化待处理学习事件")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 1000:
        parser.error("--limit 必须在 1 到 1000 之间")
    async with session_factory() as db:
        counts = await qualify_pending_events(db, limit=args.limit)
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
