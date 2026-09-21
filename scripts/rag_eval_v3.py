"""运行数据驱动的教材 RAG V3 离线评测。

用法：
  server\\.venv\\Scripts\\python.exe scripts\\rag_eval_v3.py \
    --dataset contracts/rag-eval/v3-sample.json \
    --results contracts/rag-eval/v3-run-sample.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

from app.modules.knowledge.evaluation_dataset import (  # noqa: E402
    EvaluationDataError,
    score_run,
)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 格式错误: {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="教材 RAG V3 离线评测")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = score_run(_read_json(args.dataset), _read_json(args.results), k=args.k)
    except EvaluationDataError as exc:
        raise SystemExit(f"评测数据不合法: {exc}") from exc
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
