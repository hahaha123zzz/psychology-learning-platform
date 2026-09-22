"""下载 V3 评测所需的开放教材到本地、Git 忽略的目录。

示例：
  server\\.venv\\Scripts\\python.exe scripts\\fetch_oer_test_corpus.py \\
    --source first-batch --accept-licenses

此脚本只下载官方已核验的地址。下载不等于可以把内容发送给外部模型；
具体边界见 docs/v3/2026-09-22-oer-test-corpus.md。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "oer-textbooks"
USER_AGENT = "psychology-learning-platform-v3-evaluator/1.0"

SOURCES = {
    "research-methods-psychology-4e": {
        "filename": "research-methods-in-psychology-4e.pdf",
        "url": "https://kpu.pressbooks.pub/psychmethods4e/open/download?type=pdf",
        "license": "CC BY-NC-SA 4.0",
        "usage": "local_only",
    },
    "openstax-psychology-2e": {
        "filename": "openstax-psychology-2e.pdf",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Psychology2e_WEB.pdf",
        "license": "CC BY-NC-SA 4.0",
        "usage": "local_only_no_external_generative_ai",
    },
    "intro-psychology-canadian-1e": {
        "filename": "introduction-to-psychology-canadian-1e.pdf",
        "url": "https://opentextbc.ca/introductiontopsychology/open/download?type=pdf",
        "license": "CC BY-NC-SA 4.0",
        "usage": "local_only",
    },
    "essentials-cognitive-psychology-2e": {
        "filename": "essentials-of-cognitive-psychology-2e.pdf",
        "url": "https://una.pressbooks.pub/essentials-cognitive-psychology/open/download?type=pdf",
        "license": "CC BY-NC-SA 4.0",
        "usage": "local_only",
    },
    "principles-social-psychology-2e": {
        "filename": "principles-of-social-psychology-2e.pdf",
        "url": "https://wsu.pressbooks.pub/social-psychology/open/download?type=pdf",
        "license": "CC BY-NC-SA 4.0",
        "usage": "local_only",
    },
}

FIRST_BATCH = ("research-methods-psychology-4e", "openstax-psychology-2e")


def _download(source_id: str, output_dir: Path) -> dict[str, object]:
    source = SOURCES[source_id]
    target = output_dir / source["filename"]
    temporary_path = target.with_suffix(target.suffix + ".download")
    expected_bytes: int | None = None
    content_type = ""

    # 个别 CDN 会在长连接中提前关闭响应。利用官方声明的 Range 支持续传，且在
    # 完整性通过前绝不覆盖已有的目标 PDF。
    for _attempt in range(3):
        current_bytes = temporary_path.stat().st_size if temporary_path.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if current_bytes:
            headers["Range"] = f"bytes={current_bytes}-"
        request = Request(source["url"], headers=headers)

        with urlopen(request, timeout=90) as response:
            status = response.status
            content_type = response.headers.get_content_type()
            content_length = response.headers.get("Content-Length")
            if status == 206:
                content_range = response.headers.get("Content-Range", "")
                try:
                    expected_bytes = int(content_range.rsplit("/", maxsplit=1)[1])
                except (IndexError, ValueError) as exc:
                    raise RuntimeError(f"{source_id} 缺少可用 Content-Range") from exc
            elif status == 200:
                if current_bytes:
                    # 服务端忽略 Range 时，从完整响应重新开始，避免重复拼接。
                    current_bytes = 0
                try:
                    expected_bytes = int(content_length) if content_length else None
                except ValueError as exc:
                    raise RuntimeError(f"{source_id} 返回的 Content-Length 非法") from exc
            else:
                raise RuntimeError(f"{source_id} 下载返回意外状态: {status}")

            mode = "ab" if current_bytes else "wb"
            with temporary_path.open(mode) as temporary:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)

        actual_bytes = temporary_path.stat().st_size
        if expected_bytes is None or actual_bytes == expected_bytes:
            break
    else:
        actual_bytes = temporary_path.stat().st_size if temporary_path.exists() else 0
        raise RuntimeError(
            f"{source_id} 下载不完整：获得 {actual_bytes} bytes，期望 {expected_bytes} bytes；"
            f"保留 {temporary_path.name} 以便下次续传"
        )

    with temporary_path.open("rb") as downloaded:
        if downloaded.read(5) != b"%PDF-":
            raise RuntimeError(f"{source_id} 下载结果不是 PDF（Content-Type: {content_type}）")
        downloaded.seek(-1024, 2)
        if not downloaded.read().rstrip().endswith(b"%%EOF"):
            raise RuntimeError(f"{source_id} PDF 缺少 EOF 标记")

    total_bytes = temporary_path.stat().st_size
    digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
    temporary_path.replace(target)

    return {
        "source_id": source_id,
        "filename": target.name,
        "source_url": source["url"],
        "license": source["license"],
        "usage": source["usage"],
        "content_type": content_type,
        "bytes": total_bytes,
        "sha256": digest,
        "downloaded_at": datetime.now(UTC).isoformat(),
    }


def _source_ids(selection: str) -> tuple[str, ...]:
    if selection == "first-batch":
        return FIRST_BATCH
    if selection == "all":
        return tuple(SOURCES)
    return (selection,)


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 V3 开放教材评测语料")
    parser.add_argument("--source", choices=("first-batch", "all", *SOURCES), default="first-batch")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--accept-licenses", action="store_true", help="确认已阅读并接受语料清单中的许可和使用边界")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将下载的来源")
    args = parser.parse_args()

    source_ids = _source_ids(args.source)
    if args.dry_run:
        print(json.dumps({"sources": {source_id: SOURCES[source_id] for source_id in source_ids}}, ensure_ascii=False, indent=2))
        return 0
    if not args.accept_licenses:
        parser.error("下载前必须显式传入 --accept-licenses")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [_download(source_id, output_dir) for source_id in source_ids]
    manifest = {
        "schema_version": "oer-test-corpus/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "records": records,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
