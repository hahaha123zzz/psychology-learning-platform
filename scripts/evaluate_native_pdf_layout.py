"""对本地原生 PDF 版面对象解析做可复现统计，不输出教材正文或二进制资产。"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.modules.materials.parsers.stub_pdf import StubPdfParser


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = args.pdf.read_bytes()
    result = StubPdfParser().parse(data, "application/pdf")
    object_counts = Counter(item.type for item in result.objects)
    bbox_counts = Counter(item.type for item in result.objects if item.bbox is not None)
    output = {
        "source_filename": args.pdf.name,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "parser": {"name": StubPdfParser.name, "version": StubPdfParser.version},
        "page_count": result.page_count,
        "object_counts": dict(sorted(object_counts.items())),
        "bbox_counts": dict(sorted(bbox_counts.items())),
        "asset_count": sum(1 for item in result.objects if item.asset_bytes),
        "issues": result.issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
