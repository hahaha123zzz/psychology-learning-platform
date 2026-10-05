from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from app.modules.materials.compiler import (
    BUILD_STAGES,
    BuildStage,
    CourseBuildManifest,
    PublicationLedger,
    StageStatus,
    source_validation_blocker,
)
from app.modules.materials.mapping import (
    map_ooxml_objects_to_pdf,
    verify_precise_reference_anchors,
)
from app.modules.materials.parsers.base import ParsedObject
from app.modules.materials.renderers.base import RendererUnavailableError
from app.modules.materials.renderers.formats import (
    OLE_COMPOUND_SIGNATURE,
    SourceFormat,
    inspect_source,
)
from app.modules.materials.renderers.local_office import (
    LibreOfficeRendererAdapter,
    RendererProbe,
    probe_local_renderer,
)
from app.modules.materials.renderers.pymupdf_pdf import render_pdf_page

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _minimal_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<w:document/>")
    return output.getvalue()


def _pdf_with_unicode_pages(pages: list[str]) -> bytes:
    """生成携带 ToUnicode 映射的自包含文本 PDF，不依赖系统 CJK 字体。"""
    characters = sorted(set("".join(pages)))
    assert len(characters) <= 200
    codes = {char: index + 33 for index, char in enumerate(characters)}
    cmap_rows = [
        f"<{code:02X}> <{char.encode('utf-16-be').hex().upper()}>"
        for char, code in codes.items()
    ]
    cmap = (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(cmap_rows)} beginbfchar\n"
        + "\n".join(cmap_rows)
        + "\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\n"
        "end\nend"
    ).encode("ascii")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{5 + (index * 2)} 0 R".encode() for index in range(len(pages)))
        + f"] /Count {len(pages)} >>".encode(),
        (
            f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 33 "
            f"/LastChar {32 + len(characters)} /Widths "
            f"[{' '.join('600' for _ in characters)}] /Encoding /WinAnsiEncoding "
        "/ToUnicode 4 0 R >>"
        ).encode(),
        f"<< /Length {len(cmap)} >>\nstream\n".encode() + cmap + b"\nendstream",
    ]
    for index, text in enumerate(pages):
        page_id = 5 + (index * 2)
        content_id = page_id + 1
        encoded = "".join(f"{codes[char]:02X}" for char in text)
        content = f"BT /F1 14 Tf 72 720 Td <{encoded}> Tj ET".encode()
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for object_id, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{object_id} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(offsets)}\n".encode())
    chunks.append(b"0000000000 65535 f \n")
    chunks.extend(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    chunks.append(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return b"".join(chunks)


def test_source_inspection_distinguishes_legacy_doc_from_docx() -> None:
    old_doc = OLE_COMPOUND_SIGNATURE + b"local fixture bytes"
    docx = _minimal_docx()

    old_inspection = inspect_source(old_doc, "教材.doc")
    docx_inspection = inspect_source(docx, "教材.docx")
    mismatch = inspect_source(old_doc, "renamed.docx")

    assert old_inspection.source_format is SourceFormat.LEGACY_DOC
    assert old_inspection.extension_matches
    assert docx_inspection.source_format is SourceFormat.DOCX
    assert mismatch.source_format is SourceFormat.UNKNOWN
    assert not mismatch.extension_matches
    assert mismatch.blocked_reason == "ole_container_requires_doc_extension"


def test_missing_renderer_is_a_deterministic_blocker_and_never_attempts_conversion(
    tmp_path,
) -> None:
    probe = probe_local_renderer(
        which=lambda _candidate: None,
        run=lambda *_args, **_kwargs: pytest.fail("缺少 renderer 时不应运行转换命令"),
        font_directory=tmp_path,
    )
    inspection = inspect_source(
        OLE_COMPOUND_SIGNATURE + b"fixture",
        "旧版资料.doc",
    )
    adapter = LibreOfficeRendererAdapter(probe)

    assert not probe.available
    assert probe.blocked_reason == "local_libreoffice_not_installed"
    assert probe.font_inventory_sha256 == hashlib.sha256(b"").hexdigest()
    assert source_validation_blocker(inspection, probe.manifest()) == (
        "local_libreoffice_not_installed"
    )
    with pytest.raises(RendererUnavailableError, match="local_libreoffice_not_installed"):
        adapter.render(
            OLE_COMPOUND_SIGNATURE + b"fixture",
            "application/msword",
            "旧版资料.doc",
        )


def test_legacy_doc_adapter_records_local_docx_pdf_conversion_chain() -> None:
    source = OLE_COMPOUND_SIGNATURE + b"immutable legacy DOC test fixture"
    pdf_document = pymupdf.open()
    page = pdf_document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Converted local renderer fixture")
    expected_pdf = pdf_document.tobytes()
    pdf_document.close()
    converted_docx = _minimal_docx()
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> SimpleNamespace:
        commands.append(command)
        target_format = command[command.index("--convert-to") + 1]
        output_directory = Path(command[command.index("--outdir") + 1])
        source_path = Path(command[-1])
        output = output_directory / f"{source_path.stem}.{target_format}"
        output.write_bytes(converted_docx if target_format == "docx" else expected_pdf)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    probe = RendererProbe(
        available=True,
        name="libreoffice",
        executable="soffice",
        version="LibreOffice 25.2.0.0",
        font_inventory_count=2,
        font_inventory_sha256="a" * 64,
        font_files=("fixture-cjk.ttf", "fixture-serif.otf"),
        font_substitution_status="unverified_until_conversion",
        blocked_reason=None,
        page_configuration={"page_setup": "preserve_source_document", "dpi": 144},
    )
    rendered = LibreOfficeRendererAdapter(probe, run=fake_run).render(
        source,
        "application/msword",
        "心理学资料.doc",
    )

    assert source == OLE_COMPOUND_SIGNATURE + b"immutable legacy DOC test fixture"
    assert len(commands) == 2
    assert [command[command.index("--convert-to") + 1] for command in commands] == [
        "docx",
        "pdf",
    ]
    assert Path(commands[0][-1]).suffix == ".doc"
    assert Path(commands[1][-1]).suffix == ".docx"
    assert commands[0][1] == commands[1][1]
    assert "--headless" in commands[0] and "--headless" in commands[1]
    assert rendered.intermediate_artifacts[0].content == converted_docx
    assert rendered.renderer_version == "LibreOffice 25.2.0.0"
    assert rendered.manifest()["intermediate_artifacts"][0]["sha256"] == hashlib.sha256(
        converted_docx
    ).hexdigest()
    assert rendered.manifest()["page_count"] == 1


def test_pdf_renderer_reuses_fixed_page_transform_and_hashes_assets() -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "fixed reader page")
    source = document.tobytes()
    document.close()

    rendered = LibreOfficeRendererAdapter().render(source, "application/pdf", "fixed.pdf")
    manifest = rendered.manifest()

    assert manifest["page_count"] == 1
    assert manifest["canonical_pdf_sha256"] == hashlib.sha256(
        rendered.canonical_pdf
    ).hexdigest()
    assert manifest["pages"][0]["physical_page"] == 1
    assert manifest["pages"][0]["image_sha256"] == hashlib.sha256(
        rendered.pages[0].content
    ).hexdigest()
    assert manifest["renderer_metadata"]["pdf_page_renderer"].startswith("pymupdf-")
    build = CourseBuildManifest.create(
        source_bytes=source,
        filename="fixed.pdf",
        configuration={"dpi": 144},
        renderer=probe_local_renderer(which=lambda _candidate: None).manifest(),
    )
    build = build.begin(BuildStage.VALIDATE_INPUT, build.source.sha256)
    build = build.complete(BuildStage.VALIDATE_INPUT, "1" * 64)
    build = build.begin(BuildStage.RENDER, "1" * 64)
    build = build.complete_render(manifest)
    assert build.stages[1].status is StageStatus.COMPLETED
    assert build.render_artifacts["canonical_pdf_sha256"] == manifest["canonical_pdf_sha256"]


def test_manifest_identity_is_deterministic_and_stage_failure_preserves_last_known_good() -> None:
    source = b"%PDF-1.4\nminimal input"
    renderer = {
        "available": True,
        "name": "test-renderer",
        "version": "1.0",
        "font_inventory_sha256": "a" * 64,
    }
    first = CourseBuildManifest.create(
        source_bytes=source,
        filename="book.pdf",
        configuration={"dpi": 144, "page_setup": "source"},
        renderer=renderer,
    )
    second = CourseBuildManifest.create(
        source_bytes=source,
        filename="book.pdf",
        configuration={"page_setup": "source", "dpi": 144},
        renderer=renderer,
    )
    assert first.build_id == second.build_id
    assert first.manifest()["manifest_sha256"] == second.manifest()["manifest_sha256"]

    prior = PublicationLedger(last_known_good_build_id="previous-build")
    blocked = first.begin(BuildStage.VALIDATE_INPUT, first.source.sha256)
    blocked = blocked.complete(BuildStage.VALIDATE_INPUT, "1" * 64)
    blocked = blocked.begin(BuildStage.RENDER, "1" * 64)
    blocked = blocked.fail(
        BuildStage.RENDER,
        error_code="renderer_unavailable",
        retryable=True,
        blocked=True,
    )
    assert blocked.stages[1].status is StageStatus.BLOCKED
    assert prior.preserve_after_failure(blocked) == prior

    retried = blocked.begin(BuildStage.RENDER, "1" * 64)
    retried = retried.complete(BuildStage.RENDER, "2" * 64)
    for stage in BUILD_STAGES[2:]:
        retried = retried.begin(stage, "2" * 64)
        retried = retried.complete(stage, "3" * 64)
    assert retried.publishable
    published = prior.commit(retried)
    assert published.last_known_good_build_id == first.build_id
    assert published.commit(retried) == published


def test_unique_pdf_text_mapping_ignores_docx_page_hint_and_returns_cross_page_anchors() -> None:
    heading = "第一章 绪论"
    paragraph = "实验心理学研究行为与心理过程"
    caption = "图 2.1 反应时测量"
    table = "变量 | 定义\n反应时 | 按键延迟"
    formula = "F = m a"
    cross_page = "跨页对象连接到下一页的尾部内容"
    pdf = _pdf_with_unicode_pages(
        [
            heading + paragraph + caption + table + formula + "跨页对象连接到",
            "下一页的尾部内容",
        ]
    )
    objects = [
        ParsedObject(
            type="chapter",
            raw_content=heading,
            physical_page=91,
            reading_order=1,
        ),
        ParsedObject(
            type="paragraph",
            raw_content=paragraph,
            physical_page=91,
            reading_order=2,
        ),
        ParsedObject(
            type="paragraph",
            raw_content=caption,
            physical_page=91,
            reading_order=3,
        ),
        ParsedObject(
            type="table",
            raw_content=table,
            physical_page=91,
            reading_order=4,
        ),
        ParsedObject(
            type="formula",
            raw_content=formula,
            physical_page=91,
            reading_order=5,
        ),
        ParsedObject(
            type="paragraph",
            raw_content=cross_page,
            physical_page=91,
            reading_order=6,
        ),
    ]

    extracted = pymupdf.open(stream=pdf, filetype="pdf")
    assert heading in extracted[0].get_text()
    extracted.close()
    mappings = map_ooxml_objects_to_pdf(objects, pdf)

    assert [mapping.status for mapping in mappings] == ["anchored"] * 6
    assert mappings[0].anchors[0].physical_page == 1
    assert mappings[0].anchors[0].coordinate_space == "pdf_user_bottom_left"
    assert [anchor.physical_page for anchor in mappings[5].anchors] == [1, 2]
    assert all(
        anchor.bbox[0] < anchor.bbox[2]
        for mapping in mappings
        for anchor in mapping.anchors
    )
    gate = verify_precise_reference_anchors(
        mappings,
        [mappings[0].object_fingerprint, mappings[5].object_fingerprint],
        enabled=True,
    )
    assert gate.allowed


def test_duplicate_text_and_non_text_objects_are_unsupported() -> None:
    pdf = _pdf_with_unicode_pages(["重复段落", "重复段落"])
    duplicate = ParsedObject(
        type="paragraph",
        raw_content="重复段落",
        physical_page=None,
        reading_order=1,
    )
    figure = ParsedObject(
        type="figure",
        raw_content="反应时分布图",
        physical_page=None,
        reading_order=2,
    )

    duplicate_mapping, figure_mapping = map_ooxml_objects_to_pdf([duplicate, figure], pdf)

    assert duplicate_mapping.status == "unsupported"
    assert duplicate_mapping.reason == "ambiguous_text_match"
    assert figure_mapping.status == "unsupported"
    assert figure_mapping.reason == "non_text_figure_requires_verified_layout"
    gate = verify_precise_reference_anchors(
        [duplicate_mapping, figure_mapping],
        [figure_mapping.object_fingerprint],
        enabled=True,
    )
    assert not gate.allowed
    assert gate.missing_object_fingerprints == (figure_mapping.object_fingerprint,)


def test_rotated_pdf_mapping_uses_reader_coordinate_transform() -> None:
    source = _pdf_with_unicode_pages(["旋转后的引用位置"])
    document = pymupdf.open(stream=source, filetype="pdf")
    document[0].set_rotation(90)
    rotated_pdf = document.tobytes()
    document.close()
    item = ParsedObject(
        type="paragraph",
        raw_content="旋转后的引用位置",
        physical_page=None,
        reading_order=1,
    )

    mapping = map_ooxml_objects_to_pdf([item], rotated_pdf)[0]
    page_image = render_pdf_page(rotated_pdf, 1)
    pixel_bbox = page_image.transform.pdf_bbox_to_pixels(list(mapping.anchors[0].bbox))

    assert mapping.status == "anchored"
    assert page_image.transform.rotation == 90
    assert 0 <= pixel_bbox[0] < pixel_bbox[2] <= page_image.transform.pixel_width
    assert 0 <= pixel_bbox[1] < pixel_bbox[3] <= page_image.transform.pixel_height


def test_publication_gate_blocks_unanchored_required_citations() -> None:
    source = b"%PDF-1.4\nminimal input"
    manifest = CourseBuildManifest.create(
        source_bytes=source,
        filename="book.pdf",
        configuration={"dpi": 144},
        renderer={"available": True, "name": "fixture", "version": "1"},
    )
    for stage in BUILD_STAGES[:-1]:
        manifest = manifest.begin(stage, manifest.source.sha256)
        if stage is BuildStage.RENDER:
            render_manifest = {
                "canonical_pdf_sha256": "a" * 64,
                "page_count": 1,
                "pages": [
                    {
                        "physical_page": 1,
                        "image_sha256": "b" * 64,
                    }
                ],
            }
            manifest = manifest.complete_render(render_manifest)
        else:
            manifest = manifest.complete(stage, "c" * 64)
    manifest = manifest.begin(BuildStage.PUBLICATION_GATE, "c" * 64)
    manifest = manifest.complete_publication_gate({"allowed": False}, "d" * 64)

    assert manifest.stages[-1].status is StageStatus.BLOCKED
    assert not manifest.publishable
    assert PublicationLedger().preserve_after_failure(manifest) == PublicationLedger()
