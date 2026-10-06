"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { api, ApiError } from "../../lib/api";
import { Button } from "../ui/Button";
import { ContextDrawer } from "../ui/ContextDrawer";

type EvidenceAnchor = {
  physical_page: number;
  coordinate_space: "pdf_user_bottom_left" | "unavailable" | string;
  bbox: number[] | null;
  precision?: string | null;
};

type EvidencePointerView = {
  evidence_pointer_id: string;
  material_title: string;
  material_id: string;
  material_version_id: string;
  chapter_path: string | null;
  physical_page: number | null;
  object_type: string;
  coordinate_space: "pdf_user_bottom_left" | "unavailable";
  bbox: number[] | null;
  anchors?: EvidenceAnchor[] | null;
  excerpt: string;
  excerpt_sha256: string;
};

type ReaderPage = {
  physicalPage: number;
  url: string;
  width: number;
  height: number;
  bboxPixels: [number, number, number, number];
};

const MIN_ZOOM = 0.75;
const MAX_ZOOM = 2;

function isVerifiableAnchor(anchor: unknown): anchor is EvidenceAnchor {
  if (!anchor || typeof anchor !== "object") return false;
  const candidate = anchor as EvidenceAnchor;
  return (
    Number.isInteger(candidate.physical_page) &&
    candidate.physical_page > 0 &&
    candidate.coordinate_space === "pdf_user_bottom_left" &&
    Array.isArray(candidate.bbox) &&
    candidate.bbox.length === 4 &&
    candidate.bbox.every(Number.isFinite) &&
    candidate.bbox[0] < candidate.bbox[2] &&
    candidate.bbox[1] < candidate.bbox[3]
  );
}

function anchorsFor(view: EvidencePointerView): EvidenceAnchor[] {
  const anchors = Array.isArray(view.anchors) ? view.anchors : [];
  const verified = anchors.filter(isVerifiableAnchor);
  if (verified.length) {
    const seenPages = new Set<number>();
    return verified
      .filter((anchor) => {
        if (seenPages.has(anchor.physical_page)) return false;
        seenPages.add(anchor.physical_page);
        return true;
      })
      .sort((left, right) => left.physical_page - right.physical_page);
  }

  // 兼容 0047 之前的持久单页指针；只有完整坐标才可进入固定页图流程。
  const legacy: EvidenceAnchor = {
    physical_page: view.physical_page ?? 0,
    coordinate_space: view.coordinate_space,
    bbox: view.bbox,
    precision: "legacy_pointer_bbox",
  };
  return isVerifiableAnchor(legacy) ? [legacy] : [];
}

export default function EvidencePointerDrawer({
  pointerId,
  label = "查看教材引用",
  onAskTutor,
}: {
  pointerId: string;
  label?: string;
  onAskTutor?: (evidencePointerId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [view, setView] = useState<EvidencePointerView | null>(null);
  const [selectedPhysicalPage, setSelectedPhysicalPage] = useState<number | null>(null);
  const [page, setPage] = useState<ReaderPage | null>(null);
  const [notice, setNotice] = useState("");
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);

  const anchors = useMemo(() => (view ? anchorsFor(view) : []), [view]);
  const activeAnchor = anchors.find((anchor) => anchor.physical_page === selectedPhysicalPage) ?? null;
  const activeAnchorIndex = anchors.findIndex((anchor) => anchor.physical_page === selectedPhysicalPage);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    async function loadPointer() {
      setLoading(true);
      setPageLoading(false);
      setView(null);
      setPage(null);
      setSelectedPhysicalPage(null);
      setNotice("");
      setZoom(1);
      setRotation(0);
      try {
        const result = await api<EvidencePointerView>(`/evidence-pointers/${pointerId}`);
        if (cancelled) return;
        setView(result);
        const availableAnchors = anchorsFor(result);
        const primaryPage = availableAnchors.find(
          (anchor) => anchor.physical_page === result.physical_page,
        )?.physical_page;
        setSelectedPhysicalPage(primaryPage ?? availableAnchors[0]?.physical_page ?? null);
      } catch (reason: unknown) {
        if (cancelled) return;
        setNotice(reason instanceof ApiError ? reason.message : "暂时无法读取教材来源快照。");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadPointer();
    return () => {
      cancelled = true;
    };
  }, [open, pointerId]);

  useEffect(() => {
    if (!open || !view || !activeAnchor || selectedPhysicalPage === null) {
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;

    async function loadPage() {
      setPage(null);
      setPageLoading(true);
      setNotice("");
      try {
        const query = new URLSearchParams({ physical_page: String(selectedPhysicalPage) });
        const imageResponse = await fetch(
          `/api/v1/evidence-pointers/${pointerId}/page-image?${query.toString()}`,
          { credentials: "include", cache: "no-store" },
        );
        if (!imageResponse.ok) {
          let message = "固定页图暂不可用；仍可查看下方文字来源快照。";
          try {
            const payload = (await imageResponse.json()) as { error?: { message?: string } };
            message = payload.error?.message ?? message;
          } catch {
            // 保留可读的页图降级提示。
          }
          throw new ApiError(imageResponse.status, message);
        }

        const physicalPage = Number(imageResponse.headers.get("X-Reader-Physical-Page"));
        const transform = JSON.parse(imageResponse.headers.get("X-Reader-Transform") ?? "null") as
          | { pixel_width?: number; pixel_height?: number }
          | null;
        const bboxPixels = JSON.parse(imageResponse.headers.get("X-Reader-Bbox-Pixels") ?? "null") as
          | [number, number, number, number]
          | null;
        if (
          physicalPage !== selectedPhysicalPage ||
          !transform ||
          !Number.isFinite(transform.pixel_width) ||
          !Number.isFinite(transform.pixel_height) ||
          (transform.pixel_width ?? 0) <= 0 ||
          (transform.pixel_height ?? 0) <= 0 ||
          !bboxPixels ||
          bboxPixels.length !== 4 ||
          !bboxPixels.every(Number.isFinite)
        ) {
          throw new Error("页图缺少匹配物理页的可验证坐标变换。");
        }

        objectUrl = URL.createObjectURL(await imageResponse.blob());
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setPage({
          physicalPage,
          url: objectUrl,
          width: transform.pixel_width as number,
          height: transform.pixel_height as number,
          bboxPixels,
        });
      } catch (reason: unknown) {
        if (cancelled) return;
        setNotice(
          reason instanceof ApiError
            ? reason.message
            : "暂时无法读取匹配的固定页图；文字来源快照仍可用。",
        );
      } finally {
        if (!cancelled) setPageLoading(false);
      }
    }

    void loadPage();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [activeAnchor, open, pointerId, selectedPhysicalPage, view]);

  function changeZoom(delta: number) {
    setZoom((current) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number((current + delta).toFixed(2)))));
  }

  const quarterTurn = Math.abs(rotation) % 180 === 90;
  const visiblePage = page?.physicalPage === selectedPhysicalPage ? page : null;
  const stageRatio = visiblePage
    ? quarterTurn
      ? `${visiblePage.height} / ${visiblePage.width}`
      : `${visiblePage.width} / ${visiblePage.height}`
    : undefined;
  const sourceCanvasWidth = visiblePage && quarterTurn
    ? `calc(100% * ${visiblePage.width / visiblePage.height})`
    : "100%";

  return (
    <>
      <Button
        className="evidence-pointer-trigger"
        onClick={() => {
          setView(null);
          setNotice("");
          setLoading(true);
          setOpen(true);
        }}
        type="button"
        variant="link"
      >
        {label}
      </Button>
      <ContextDrawer
        labelledBy={`evidence-pointer-${pointerId}`}
        onClose={() => setOpen(false)}
        open={open}
        title="教材来源快照"
      >
        {loading && <p aria-live="polite" className="status-banner">正在重新校验权限并读取引用…</p>}
        {pageLoading && <p aria-live="polite" className="status-banner">正在读取物理页 {selectedPhysicalPage}…</p>}
        {notice && <p aria-live="polite" className="status-banner">{notice}</p>}
        {view && (
          <article className="evidence-pointer-view">
            <h3>{view.material_title}</h3>
            <p>
              {view.chapter_path || "未记录章节"}
              {view.physical_page ? ` · 物理页 ${view.physical_page}` : " · 原始解析未声明物理页"}
              {` · ${view.object_type}`}
            </p>
            {anchors.length > 0 && (
              <section aria-label="引用页图控制" className="reader-controls">
                <div className="reader-page-controls">
                  <label htmlFor={`reader-page-${pointerId}`}>引用定位页</label>
                  <select
                    id={`reader-page-${pointerId}`}
                    onChange={(event) => setSelectedPhysicalPage(Number(event.target.value))}
                    value={selectedPhysicalPage ?? ""}
                  >
                    {anchors.map((anchor, index) => (
                      <option key={anchor.physical_page} value={anchor.physical_page}>
                        物理页 {anchor.physical_page}（{index + 1}/{anchors.length}）
                      </option>
                    ))}
                  </select>
                  <span aria-live="polite">
                    {activeAnchorIndex >= 0 ? `${activeAnchorIndex + 1} / ${anchors.length} 页` : "未选择定位页"}
                  </span>
                </div>
                <div aria-label="页图显示控制" className="reader-view-controls" role="group">
                  <Button
                    aria-label="缩小页图"
                    disabled={zoom <= MIN_ZOOM}
                    onClick={() => changeZoom(-0.25)}
                    type="button"
                    variant="secondary"
                  >
                    −
                  </Button>
                  <span aria-live="polite">{Math.round(zoom * 100)}%</span>
                  <Button
                    aria-label="放大页图"
                    disabled={zoom >= MAX_ZOOM}
                    onClick={() => changeZoom(0.25)}
                    type="button"
                    variant="secondary"
                  >
                    +
                  </Button>
                  <Button
                    aria-label="逆时针旋转页图"
                    onClick={() => setRotation((current) => (current - 90 + 360) % 360)}
                    type="button"
                    variant="secondary"
                  >
                    ↶
                  </Button>
                  <Button
                    aria-label="顺时针旋转页图"
                    onClick={() => setRotation((current) => (current + 90) % 360)}
                    type="button"
                    variant="secondary"
                  >
                    ↷
                  </Button>
                </div>
              </section>
            )}
            {visiblePage && activeAnchor && (
              <figure style={{ margin: "1.25rem 0", textAlign: "center" }}>
                <div
                  aria-label={`物理页 ${visiblePage.physicalPage} 页图与引用高亮`}
                  className="reader-image-viewport"
                  style={{ maxHeight: "min(72vh, 70rem)", overflow: "auto" }}
                >
                  <div
                    className="reader-image-stage"
                    style={{
                      aspectRatio: stageRatio,
                      margin: "0 auto",
                      maxWidth: zoom <= 1 ? "56rem" : undefined,
                      position: "relative",
                      width: `${zoom * 100}%`,
                    }}
                  >
                    <div
                      style={{
                        left: "50%",
                        position: "absolute",
                        top: "50%",
                        transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
                        transformOrigin: "center",
                        width: sourceCanvasWidth,
                      }}
                    >
                      <Image
                        src={visiblePage.url}
                        alt={`教材物理页 ${visiblePage.physicalPage}，红框标出引用位置`}
                        width={visiblePage.width}
                        height={visiblePage.height}
                        unoptimized
                        style={{ display: "block", height: "auto", width: "100%" }}
                      />
                      <span
                        aria-hidden="true"
                        style={{
                          background: "rgba(235, 70, 65, 0.12)",
                          border: "2px solid #d8423a",
                          boxSizing: "border-box",
                          height: `${((visiblePage.bboxPixels[3] - visiblePage.bboxPixels[1]) / visiblePage.height) * 100}%`,
                          left: `${(visiblePage.bboxPixels[0] / visiblePage.width) * 100}%`,
                          pointerEvents: "none",
                          position: "absolute",
                          top: `${(visiblePage.bboxPixels[1] / visiblePage.height) * 100}%`,
                          width: `${((visiblePage.bboxPixels[2] - visiblePage.bboxPixels[0]) / visiblePage.width) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
                <figcaption>
                  物理页 {visiblePage.physicalPage} · 红框为经坐标变换定位的来源对象
                  {activeAnchor.precision ? ` · ${activeAnchor.precision}` : ""}
                </figcaption>
              </figure>
            )}
            <blockquote>
              {view.excerpt || (view.object_type === "figure"
                ? "该对象只保存了图像位置；系统未解析图像含义。"
                : "此对象没有可显示的文字摘录。")}
            </blockquote>
            {view.object_type === "figure" && !view.excerpt.trim() && (
              <p className="evidence-pointer-limitation">
                图像语义尚未解析；当前只能定位，不能据此解释图像内容。
              </p>
            )}
            {view.object_type === "table" && view.excerpt.trim() && onAskTutor && (
              <Button
                onClick={() => {
                  onAskTutor(view.evidence_pointer_id);
                  setOpen(false);
                }}
                type="button"
                variant="secondary"
              >
                向 Tutor 提问
              </Button>
            )}
            <dl>
              <div><dt>教材版本</dt><dd>{view.material_version_id}</dd></div>
              <div><dt>引用校验</dt><dd>SHA-256 {view.excerpt_sha256}</dd></div>
              <div>
                <dt>当前定位</dt>
                <dd>
                  {activeAnchor
                    ? `物理页 ${activeAnchor.physical_page} · PDF 用户空间（左下原点）：${activeAnchor.bbox?.join(", ")}`
                    : "暂无可验证的页内坐标"}
                </dd>
              </div>
            </dl>
            {!visiblePage && !pageLoading && (
              <p className="evidence-pointer-limitation">
                {activeAnchor
                  ? "固定页图暂不可用；上方仍保留经重新鉴权的文字快照与定位坐标。"
                  : "该来源没有可验证的物理页和 PDF 页内坐标；不伪造页图或高亮，以上文字快照仍绑定生成时教材版本。"}
              </p>
            )}
          </article>
        )}
      </ContextDrawer>
    </>
  );
}
