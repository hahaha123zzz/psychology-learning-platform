"""可选的本地 LibreOffice 转换适配器；不下载、安装或调用外部服务。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.modules.materials.renderers.base import (
    RenderedArtifact,
    RenderedDocument,
    RendererUnavailableError,
)
from app.modules.materials.renderers.formats import SourceFormat, inspect_source
from app.modules.materials.renderers.pymupdf_pdf import RENDERER_VERSION, render_pdf_page

LIBREOFFICE_CANDIDATES = ("soffice", "soffice.exe", "libreoffice")
PDF_NORMALIZATION_VERSION = "pdf-metadata-clean-v1"
DEFAULT_RENDER_CONFIGURATION = {
    "page_setup": "preserve_source_document",
    "image_format": "png",
    "dpi": 144,
    "colorspace": "rgb",
    "alpha": False,
    "pdf_normalization": PDF_NORMALIZATION_VERSION,
}


@dataclass(frozen=True)
class RendererProbe:
    available: bool
    name: str
    executable: str | None
    version: str | None
    font_inventory_count: int
    font_inventory_sha256: str
    font_files: tuple[str, ...]
    font_substitution_status: str
    blocked_reason: str | None
    page_configuration: dict[str, str | int | bool]

    def manifest(self) -> dict[str, str | int | bool | list[str] | None]:
        return {
            "available": self.available,
            "name": self.name,
            "executable": self.executable,
            "version": self.version,
            "font_inventory_count": self.font_inventory_count,
            "font_inventory_sha256": self.font_inventory_sha256,
            "font_files": list(self.font_files),
            "font_substitution_status": self.font_substitution_status,
            "blocked_reason": self.blocked_reason,
            "page_configuration": dict(self.page_configuration),
        }


def _font_inventory(font_directory: Path | None = None) -> tuple[tuple[str, ...], str]:
    if font_directory is None:
        windows_root = os.environ.get("WINDIR")
        candidates = (
            [Path(windows_root) / "Fonts"] if windows_root else []
        ) + [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
        ]
        font_directory = next((path for path in candidates if path.is_dir()), None)

    names: list[str] = []
    if font_directory is not None and font_directory.is_dir():
        try:
            names = sorted(
                path.name
                for path in font_directory.iterdir()
                if path.is_file()
                and path.suffix.lower() in {".ttf", ".otf", ".ttc", ".fon"}
            )
        except OSError:
            names = []
    inventory_payload = "\n".join(names).encode("utf-8")
    return tuple(names), hashlib.sha256(inventory_payload).hexdigest()


def probe_local_renderer(
    *,
    executable: str | None = None,
    which=None,
    run=None,
    font_directory: Path | None = None,
) -> RendererProbe:
    """只探测本地 LibreOffice；缺失时给出确定阻塞原因。"""
    find_executable = which or shutil.which
    run_command = run or subprocess.run
    detected = executable or next(
        (found for candidate in LIBREOFFICE_CANDIDATES if (found := find_executable(candidate))),
        None,
    )
    version: str | None = None
    blocked_reason: str | None = None
    if detected is None:
        blocked_reason = "local_libreoffice_not_installed"
    else:
        try:
            completed = run_command(
                [detected, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (completed.stdout or completed.stderr or "").strip()
            if completed.returncode == 0 and output:
                version = output.splitlines()[0][:200]
            else:
                blocked_reason = "local_libreoffice_version_probe_failed"
        except (OSError, subprocess.SubprocessError):
            blocked_reason = "local_libreoffice_version_probe_failed"

    font_files, font_hash = _font_inventory(font_directory)
    return RendererProbe(
        available=detected is not None and version is not None,
        name="libreoffice",
        executable=detected,
        version=version,
        font_inventory_count=len(font_files),
        font_inventory_sha256=font_hash,
        font_files=font_files,
        font_substitution_status="unverified_until_conversion",
        blocked_reason=blocked_reason,
        page_configuration=dict(DEFAULT_RENDER_CONFIGURATION),
    )


def _normalize_pdf_metadata(data: bytes) -> bytes:
    """移除常见时间/工具元数据，保留页面内容和几何。"""
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        metadata = dict(document.metadata or {})
        for key in ("creationDate", "modDate", "producer", "creator"):
            if key in metadata:
                metadata[key] = ""
        document.set_metadata(metadata)
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()


class LibreOfficeRendererAdapter:
    """DOC/DOCX 转换适配器；所有执行都落在本地临时目录中。"""

    name = "libreoffice"

    def __init__(
        self,
        probe: RendererProbe | None = None,
        *,
        timeout_seconds: int = 120,
        run=None,
    ) -> None:
        self.probe = probe or probe_local_renderer()
        self.timeout_seconds = timeout_seconds
        self._run = run or subprocess.run

    @property
    def version(self) -> str:
        return self.probe.version or "unavailable"

    def render(
        self,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> RenderedDocument:
        default_name = {
            "application/pdf": "document.pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                "document.docx"
            ),
            "application/msword": "document.doc",
        }.get(content_type, filename or "document")
        inspection = inspect_source(data, filename or default_name)
        if not inspection.extension_matches:
            raise ValueError(
                inspection.blocked_reason or "filename_extension_does_not_match_file_signature"
            )
        if inspection.source_format is SourceFormat.PDF:
            try:
                canonical_pdf = _normalize_pdf_metadata(data)
            except Exception as exc:  # noqa: BLE001
                raise RendererUnavailableError(
                    "PDF 元数据规范化失败；未生成固定产物"
                ) from exc
            return self._render_pdf(
                canonical_pdf,
                (),
                renderer_name="source_pdf_passthrough",
                renderer_version=PDF_NORMALIZATION_VERSION,
            )
        if inspection.source_format not in {SourceFormat.DOCX, SourceFormat.LEGACY_DOC}:
            raise ValueError(inspection.blocked_reason or "unsupported_document_format")
        if not self.probe.available or self.probe.executable is None:
            raise RendererUnavailableError(
                self.probe.blocked_reason or "local_document_renderer_unavailable"
            )

        with tempfile.TemporaryDirectory(prefix="psychology-render-") as temp_name:
            root = Path(temp_name)
            source_path = root / inspection.filename
            source_path.write_bytes(data)
            output_directory = root / "output"
            output_directory.mkdir()
            profile_uri = (root / "profile").as_uri()
            intermediate: tuple[RenderedArtifact, ...] = ()

            if inspection.source_format is SourceFormat.LEGACY_DOC:
                converted_docx = self._convert(
                    source_path=source_path,
                    output_directory=output_directory,
                    target_format="docx",
                    profile_uri=profile_uri,
                )
                intermediate = (
                    RenderedArtifact(
                        name="converted.docx",
                        content=converted_docx,
                        mime_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                    ),
                )
                source_path = output_directory / f"{source_path.stem}.docx"

            pdf_bytes = self._convert(
                source_path=source_path,
                output_directory=output_directory,
                target_format="pdf",
                profile_uri=profile_uri,
            )
            try:
                canonical_pdf = _normalize_pdf_metadata(pdf_bytes)
            except Exception as exc:  # noqa: BLE001
                raise RendererUnavailableError(
                    "LibreOffice PDF 元数据规范化失败；未生成固定产物"
                ) from exc
            return self._render_pdf(
                canonical_pdf,
                intermediate,
                renderer_name=self.name,
                renderer_version=self.version,
            )

    def _convert(
        self,
        *,
        source_path: Path,
        output_directory: Path,
        target_format: str,
        profile_uri: str,
    ) -> bytes:
        assert self.probe.executable is not None
        command = [
            self.probe.executable,
            f"-env:UserInstallation={profile_uri}",
            "--headless",
            "--convert-to",
            target_format,
            "--outdir",
            str(output_directory),
            str(source_path),
        ]
        try:
            completed = self._run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=source_path.parent,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RendererUnavailableError(
                "本地 LibreOffice 转换失败；未生成可用产物"
            ) from exc
        output_path = output_directory / f"{source_path.stem}.{target_format}"
        if completed.returncode != 0 or not output_path.is_file():
            raise RendererUnavailableError(
                "本地 LibreOffice 转换失败；未生成可用产物"
            )
        return output_path.read_bytes()

    def _render_pdf(
        self,
        canonical_pdf: bytes,
        intermediate: tuple[RenderedArtifact, ...],
        *,
        renderer_name: str,
        renderer_version: str,
    ) -> RenderedDocument:
        try:
            document = pymupdf.open(stream=canonical_pdf, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise RendererUnavailableError("标准 PDF 无法由 PyMuPDF 读取") from exc
        try:
            if document.is_encrypted or document.page_count < 1:
                raise RendererUnavailableError("标准 PDF 页面不可用")
            page_count = document.page_count
        finally:
            document.close()
        pages = [
            render_pdf_page(canonical_pdf, physical_page)
            for physical_page in range(1, page_count + 1)
        ]
        return RenderedDocument(
            canonical_pdf=canonical_pdf,
            pages=pages,
            renderer_name=renderer_name,
            renderer_version=renderer_version,
            intermediate_artifacts=intermediate,
            renderer_metadata={
                "font_inventory_sha256": self.probe.font_inventory_sha256,
                "font_inventory_count": self.probe.font_inventory_count,
                "font_substitution_status": self.probe.font_substitution_status,
                "page_configuration_sha256": hashlib.sha256(
                    json.dumps(
                        self.probe.page_configuration,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "pdf_normalization": PDF_NORMALIZATION_VERSION,
                "pdf_page_renderer": RENDERER_VERSION,
                "font_files": list(self.probe.font_files),
            },
        )
