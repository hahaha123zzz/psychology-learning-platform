"""只按文件签名和容器结构识别教材输入；扩展名只用于校验。"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath

OLE_COMPOUND_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class SourceFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    LEGACY_DOC = "legacy_doc"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceInspection:
    source_format: SourceFormat
    filename: str
    extension: str
    byte_length: int
    sha256: str
    signature: str
    extension_matches: bool
    blocked_reason: str | None = None

    def manifest(self) -> dict[str, str | int | bool | None]:
        return {
            "source_format": self.source_format.value,
            "filename": self.filename,
            "extension": self.extension,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "signature": self.signature,
            "extension_matches": self.extension_matches,
            "blocked_reason": self.blocked_reason,
        }


def inspect_source(data: bytes, filename: str | None = None) -> SourceInspection:
    """识别 PDF、OOXML DOCX 和 OLE Word DOC；不尝试转换或读取正文。"""
    import hashlib

    name = PurePath(filename or "upload").name
    extension = PurePath(name).suffix.lower()
    signature = data[:8].hex().upper() if data else "EMPTY"
    source_format = SourceFormat.UNKNOWN
    reason: str | None = None

    if not data:
        reason = "empty_input"
    elif data.startswith(b"%PDF-"):
        source_format = SourceFormat.PDF
    elif data.startswith(OLE_COMPOUND_SIGNATURE):
        if extension == ".doc":
            source_format = SourceFormat.LEGACY_DOC
        else:
            reason = "ole_container_requires_doc_extension"
    elif data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                names = set(package.namelist())
                is_docx = (
                    "word/document.xml" in names
                    and "[Content_Types].xml" in names
                )
        except (OSError, zipfile.BadZipFile):
            is_docx = False
        if is_docx:
            source_format = SourceFormat.DOCX
        else:
            reason = "zip_container_is_not_ooxml_docx"
    else:
        reason = "unrecognized_file_signature"

    expected_extensions = {
        SourceFormat.PDF: {".pdf"},
        SourceFormat.DOCX: {".docx"},
        SourceFormat.LEGACY_DOC: {".doc"},
    }
    extension_matches = (
        source_format is not SourceFormat.UNKNOWN
        and extension in expected_extensions[source_format]
    )
    if source_format is not SourceFormat.UNKNOWN and not extension_matches:
        reason = "filename_extension_does_not_match_file_signature"

    return SourceInspection(
        source_format=source_format,
        filename=name,
        extension=extension,
        byte_length=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        signature=signature,
        extension_matches=extension_matches,
        blocked_reason=reason,
    )
