"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import { adminOperationKey, clearAdminOperationKey, listAdminJobs, retryAdminJob, type AdminJob, type AdminOperationKeyCache } from "../lib/admin-api";
import AdminConfirmationDialog from "./AdminConfirmationDialog";
import { useAdminWriteGate } from "../app/admin/useAdminWriteGate";

const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "任务操作失败，请刷新状态后重试。";
const conflictText = (error: unknown) => error instanceof ApiError && error.status === 409
  ? "任务版本已变化（409）；已重新读取任务状态，请检查最新阶段、进度和尝试次数后再决定是否重试。"
  : explain(error);
const jobLabel = (kind: AdminJob["kind"]) => kind === "material_parse" ? "教材解析" : "教材索引";
const statusLabel: Record<AdminJob["status"] | "all", string> = {
  all: "全部状态", queued: "排队中", running: "执行中", failed: "失败", succeeded: "已完成", cancelled: "已取消",
};

export default function AdminJobsPanel() {
  const operationKeys = useRef<AdminOperationKeyCache>(new Map());
  const listRequestVersion = useRef(0);
  const { canWrite, viewportReady, isNarrow } = useAdminWriteGate();
  const [items, setItems] = useState<AdminJob[]>([]);
  const [status, setStatus] = useState<AdminJob["status"] | "all">("all");
  const [limit, setLimit] = useState(50);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("正在读取同机构教材任务…");
  const [noticeIsError, setNoticeIsError] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ job: AdminJob; reason: string } | null>(null);

  const load = useCallback(async (cursor?: string, append = false) => {
    const requestVersion = ++listRequestVersion.current;
    setListLoading(true);
    try {
      const next = await listAdminJobs(status, { limit, cursor });
      if (requestVersion !== listRequestVersion.current) return false;
      setItems((current) => append ? [...current, ...next.items] : next.items);
      setNextCursor(next.nextCursor);
      setHasMore(next.hasMore);
      setNotice("");
      setNoticeIsError(false);
      return true;
    } catch (error) {
      if (requestVersion === listRequestVersion.current) { setNotice(explain(error)); setNoticeIsError(true); }
      return false;
    } finally {
      if (requestVersion === listRequestVersion.current) setListLoading(false);
    }
  }, [status, limit]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!canWrite) setPending(null); }, [canWrite]);

  function requestRetry(job: AdminJob, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = reasons[job.id]?.trim() ?? "";
    if (!canWrite || !job.retryable || job.status !== "failed" || job.attempt_count >= 5 || reason.length < 8) return;
    setPending({ job, reason });
  }

  async function confirmRetry() {
    if (!pending || !canWrite || busy) return;
    const { job, reason } = pending;
    setBusy(true);
    try {
      const input = { version: job.version, reason };
      const operation = `retry:${job.id}`;
      const result = await retryAdminJob(job.id, job.version, reason, adminOperationKey(operationKeys.current, operation, input));
      clearAdminOperationKey(operationKeys.current, operation);
      setReasons((current) => ({ ...current, [job.id]: "" }));
      setPending(null);
      await load();
      setNotice(`任务已重新排队：${result.id} · ${statusLabel[result.status]} · v${result.version} · 尝试 ${result.attempt_count}/5。`);
      setNoticeIsError(false);
    } catch (error) {
      setPending(null);
      const refreshed = await load();
      setNotice(`${conflictText(error)}${refreshed ? " 当前任务状态已刷新；请确认当前版本和阶段后再决定下一步。" : " 刷新失败，请先重试刷新。"}`);
      setNoticeIsError(true);
    } finally { setBusy(false); }
  }

  return <section className="data-panel">
    <div className="panel-heading">
      <div><h2>教材任务与恢复</h2><p>只展示同机构解析/索引任务的状态元数据，不读取任务正文或错误详情。</p></div>
      <div className="admin-job-panel-actions">
        <label>状态<select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>每页<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option><option value={200}>200</option></select></label>
        <button className="secondary-button" type="button" onClick={() => void load()} disabled={listLoading}>刷新</button>
      </div>
    </div>
    {notice && <p className="status-banner" role={noticeIsError ? "alert" : "status"}>{notice}</p>}
    {viewportReady && isNarrow && <p className="status-banner" role="status">窄屏只读：任务重试可能触发后台工作，请使用宽屏复核后操作；当前仍可筛选和查看状态。</p>}
    <p className="empty-state">可按状态和每页条数逐页读取；已加载 {items.length} 条{hasMore ? "，还有更多记录" : "，没有更多记录"}。失败详情仅显示是否存在，不暴露原始错误内容。</p>
    {listLoading && <p className="status-banner" role="status">正在读取同机构任务…</p>}
    {items.length ? items.map((job) => {
      const reason = reasons[job.id] ?? "";
      const canRetry = job.status === "failed" && job.retryable && job.attempt_count < 5;
      return <article className="question-card" key={job.id}>
        <div>
          <strong>{jobLabel(job.kind)} · {statusLabel[job.status]}</strong>
          <small>任务 {job.id} · 阶段：{job.stage ?? "—"} · 进度：{job.progress}%</small>
          <small>课程 Scope：{job.course_id} · 尝试次数：{job.attempt_count}/5 · 版本：v{job.version}</small>
          {job.has_error && <small>存在失败信息；原始错误详情不在管理员面板展示。</small>}
        </div>
        {canRetry && canWrite ? <details>
          <summary>受控重试</summary>
          <form className="stack-form" onSubmit={(event) => requestRetry(job, event)}>
            <label>重试原因（必填，至少 8 个字符）<textarea value={reason} onChange={(event) => setReasons((current) => ({ ...current, [job.id]: event.target.value }))} minLength={8} maxLength={500} required /></label>
            <small>仅对可重试失败任务开放；需使用当前版本并记录管理员、理由和任务版本。</small>
            <button className="secondary-button" type="submit" disabled={busy || reason.trim().length < 8}>复核后重试</button>
          </form>
        </details> : job.status === "failed" && <small>{job.attempt_count >= 5 ? "已达到 5 次尝试上限。" : canWrite ? "此任务不可自动重试，请先排查。" : "窄屏只读，不能重试任务。"}</small>}
      </article>;
    }) : !notice && !listLoading && <p className="empty-state">当前筛选下没有同机构教材任务。</p>}
    {hasMore && nextCursor && <button className="secondary-button" type="button" disabled={listLoading} onClick={() => void load(nextCursor, true)}>{listLoading ? "正在读取…" : "加载更多任务"}</button>}
    <AdminConfirmationDialog
      open={Boolean(pending)}
      title="复核任务重试"
      summary={pending ? `将重新排队任务 ${pending.job.id}（${jobLabel(pending.job.kind)}，版本 v${pending.job.version}，阶段 ${pending.job.stage ?? "—"}）。` : ""}
      impact={pending ? `当前尝试 ${pending.job.attempt_count}/5；仅同机构可重试、状态为失败且 retryable 的任务可执行。不会展示原始错误详情。` : ""}
      reason={pending?.reason ?? ""}
      confirmLabel="确认重新排队"
      busy={busy}
      onConfirm={() => void confirmRetry()}
      onCancel={() => setPending(null)}
    />
  </section>;
}
