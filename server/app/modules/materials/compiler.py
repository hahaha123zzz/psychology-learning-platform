"""教材固定构建的确定性 manifest 与可恢复阶段合同。

此模块只描述一次构建，不执行数据库、对象存储、索引或发布副作用。
这些副作用必须由拥有对应服务边界的调用方提交。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from app.modules.materials.renderers.formats import SourceInspection, inspect_source

COMPILER_VERSION = "course-compiler-contract-v1"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,79}")


class BuildStage(StrEnum):
    VALIDATE_INPUT = "validate_input"
    RENDER = "render"
    ALIGN_OBJECTS = "align_objects"
    STORE_ASSETS = "store_assets"
    BUILD_INDEX = "build_index"
    PUBLICATION_GATE = "publication_gate"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


BUILD_STAGES = tuple(BuildStage)


@dataclass(frozen=True)
class StageReceipt:
    stage: BuildStage
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    input_sha256: str | None = None
    output_sha256: str | None = None
    error_code: str | None = None
    retryable: bool = False

    def manifest(self) -> dict[str, str | int | bool | None]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "attempts": self.attempts,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "error_code": self.error_code,
            "retryable": self.retryable,
        }


def _canonical_sha256(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class CourseBuildManifest:
    build_id: str
    compiler_version: str
    source: SourceInspection
    configuration: dict[str, Any]
    configuration_sha256: str
    renderer: dict[str, Any]
    renderer_sha256: str
    stages: tuple[StageReceipt, ...]
    publication_effect_id: str
    render_artifacts: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        source_bytes: bytes,
        filename: str,
        configuration: dict[str, Any],
        renderer: dict[str, Any],
    ) -> CourseBuildManifest:
        source = inspect_source(source_bytes, filename)
        configuration_copy = json.loads(
            json.dumps(configuration, ensure_ascii=False, sort_keys=True)
        )
        renderer_copy = json.loads(json.dumps(renderer, ensure_ascii=False, sort_keys=True))
        configuration_sha256 = _canonical_sha256(configuration_copy)
        renderer_sha256 = _canonical_sha256(renderer_copy)
        build_id = _canonical_sha256(
            {
                "compiler_version": COMPILER_VERSION,
                "source_sha256": source.sha256,
                "source_format": source.source_format.value,
                "configuration_sha256": configuration_sha256,
                "renderer_sha256": renderer_sha256,
            }
        )
        return cls(
            build_id=build_id,
            compiler_version=COMPILER_VERSION,
            source=source,
            configuration=configuration_copy,
            configuration_sha256=configuration_sha256,
            renderer=renderer_copy,
            renderer_sha256=renderer_sha256,
            stages=tuple(StageReceipt(stage=stage) for stage in BUILD_STAGES),
            publication_effect_id=build_id,
        )

    @property
    def publishable(self) -> bool:
        return all(receipt.status is StageStatus.COMPLETED for receipt in self.stages)

    def manifest(self) -> dict[str, Any]:
        content = {
            "build_id": self.build_id,
            "compiler_version": self.compiler_version,
            "source": self.source.manifest(),
            "configuration": self.configuration,
            "configuration_sha256": self.configuration_sha256,
            "renderer": self.renderer,
            "renderer_sha256": self.renderer_sha256,
            "render_artifacts": self.render_artifacts,
            "stages": [receipt.manifest() for receipt in self.stages],
            "publication_effect_id": self.publication_effect_id,
            "publishable": self.publishable,
        }
        content["manifest_sha256"] = _canonical_sha256(content)
        return content

    def begin(self, stage: BuildStage, input_sha256: str) -> CourseBuildManifest:
        if not _SHA256_PATTERN.fullmatch(input_sha256):
            raise ValueError("阶段输入必须是小写 SHA-256")
        index = BUILD_STAGES.index(stage)
        if any(
            receipt.status is not StageStatus.COMPLETED
            for receipt in self.stages[:index]
        ):
            raise ValueError("必须按顺序完成前置构建阶段")
        receipt = self.stages[index]
        if receipt.status is StageStatus.COMPLETED:
            if receipt.input_sha256 != input_sha256:
                raise ValueError("已完成阶段的输入摘要不可变")
            return self
        if receipt.status is StageStatus.RUNNING:
            raise ValueError("阶段已在执行，不能重复启动")
        if receipt.status in {StageStatus.FAILED, StageStatus.BLOCKED} and not receipt.retryable:
            raise ValueError("该阶段失败不可重试")
        updated = replace(
            receipt,
            status=StageStatus.RUNNING,
            attempts=receipt.attempts + 1,
            input_sha256=input_sha256,
            output_sha256=None,
            error_code=None,
            retryable=False,
        )
        return self._with_receipt(index, updated)

    def complete(self, stage: BuildStage, output_sha256: str) -> CourseBuildManifest:
        if not _SHA256_PATTERN.fullmatch(output_sha256):
            raise ValueError("阶段输出必须是小写 SHA-256")
        index = BUILD_STAGES.index(stage)
        receipt = self.stages[index]
        if receipt.status is not StageStatus.RUNNING:
            raise ValueError("只有执行中的阶段可以完成")
        return self._with_receipt(
            index,
            replace(
                receipt,
                status=StageStatus.COMPLETED,
                output_sha256=output_sha256,
                error_code=None,
                retryable=False,
            ),
        )

    def complete_render(self, render_manifest: dict[str, Any]) -> CourseBuildManifest:
        """把转换 DOCX、标准 PDF 和各页图摘要作为同一阶段收据固定下来。"""
        index = BUILD_STAGES.index(BuildStage.RENDER)
        receipt = self.stages[index]
        if receipt.status is not StageStatus.RUNNING:
            raise ValueError("只有执行中的 render 阶段可以记录产物")
        pdf_sha256 = render_manifest.get("canonical_pdf_sha256")
        pages = render_manifest.get("pages")
        page_count = render_manifest.get("page_count")
        if (
            not isinstance(pdf_sha256, str)
            or not _SHA256_PATTERN.fullmatch(pdf_sha256)
            or not isinstance(pages, list)
            or type(page_count) is not int
            or page_count < 1
            or len(pages) != page_count
        ):
            raise ValueError("render manifest 缺少可核对的 PDF/页图摘要")
        for expected_page, page in enumerate(pages, start=1):
            if (
                not isinstance(page, dict)
                or page.get("physical_page") != expected_page
                or not isinstance(page.get("image_sha256"), str)
                or not _SHA256_PATTERN.fullmatch(page["image_sha256"])
            ):
                raise ValueError("render manifest 页图编号或摘要不连续")
        copied = json.loads(json.dumps(render_manifest, ensure_ascii=False, sort_keys=True))
        digest = _canonical_sha256(copied)
        updated = self._with_receipt(
            index,
            replace(
                receipt,
                status=StageStatus.COMPLETED,
                output_sha256=digest,
                error_code=None,
                retryable=False,
            ),
        )
        return replace(updated, render_artifacts=copied)

    def complete_publication_gate(
        self,
        gate_result: dict[str, Any],
        output_sha256: str,
    ) -> CourseBuildManifest:
        """只有精确引用门禁通过时才完成最后阶段。"""
        if gate_result.get("allowed") is True:
            return self.complete(BuildStage.PUBLICATION_GATE, output_sha256)
        return self.fail(
            BuildStage.PUBLICATION_GATE,
            error_code="precise_reference_anchor_missing",
            retryable=False,
            blocked=True,
        )

    def fail(
        self,
        stage: BuildStage,
        *,
        error_code: str,
        retryable: bool,
        blocked: bool = False,
    ) -> CourseBuildManifest:
        if not _CODE_PATTERN.fullmatch(error_code):
            raise ValueError("阶段错误码格式无效")
        index = BUILD_STAGES.index(stage)
        receipt = self.stages[index]
        if receipt.status is not StageStatus.RUNNING:
            raise ValueError("只有执行中的阶段可以失败")
        return self._with_receipt(
            index,
            replace(
                receipt,
                status=StageStatus.BLOCKED if blocked else StageStatus.FAILED,
                output_sha256=None,
                error_code=error_code,
                retryable=retryable,
            ),
        )

    def _with_receipt(self, index: int, receipt: StageReceipt) -> CourseBuildManifest:
        stages = list(self.stages)
        stages[index] = receipt
        return replace(self, stages=tuple(stages))


@dataclass(frozen=True)
class PublicationLedger:
    """本地纯数据合同：失败不会推进 LKG，重复 build_id 不重复发布。"""

    last_known_good_build_id: str | None = None
    published_build_ids: tuple[str, ...] = ()

    def commit(self, manifest: CourseBuildManifest) -> PublicationLedger:
        if not manifest.publishable:
            raise ValueError("构建阶段未全部成功，不能发布")
        if manifest.publication_effect_id in self.published_build_ids:
            return self
        return PublicationLedger(
            last_known_good_build_id=manifest.build_id,
            published_build_ids=(*self.published_build_ids, manifest.publication_effect_id),
        )

    def preserve_after_failure(self, manifest: CourseBuildManifest) -> PublicationLedger:
        if manifest.publishable:
            raise ValueError("成功构建应通过 commit 推进发布状态")
        return self


def source_validation_blocker(inspection: SourceInspection, renderer: dict[str, Any]) -> str | None:
    """在转换前给出输入签名或本地 renderer 的明确阻塞原因。"""
    if inspection.source_format.value == "unknown" or not inspection.extension_matches:
        return inspection.blocked_reason or "unsupported_source_format"
    if inspection.source_format.value in {"legacy_doc", "docx"}:
        if renderer.get("available") is not True:
            return str(renderer.get("blocked_reason") or "local_document_renderer_unavailable")
    return None
