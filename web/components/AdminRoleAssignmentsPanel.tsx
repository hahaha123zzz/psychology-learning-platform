"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import {
  grantRoleAssignment,
  adminOperationKey,
  clearAdminOperationKey,
  listRoleAssignmentCourses,
  listRoleAssignments,
  revokeRoleAssignment,
  searchRoleAssignmentTargets,
  type CourseScopeOption,
  type AdminOperationKeyCache,
  type RoleAssignment,
  type RoleAssignmentTarget,
} from "../lib/admin-api";
import AdminConfirmationDialog from "./AdminConfirmationDialog";
import { useAdminWriteGate } from "../app/admin/useAdminWriteGate";

const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "授权操作失败，请稍后重试。";
const conflictText = (error: unknown) => error instanceof ApiError && error.status === 409
  ? "服务器记录已变化（409）；列表已尝试刷新，请核对最新版本与授权范围后重新发起操作。"
  : explain(error);
type ScopeType = "platform" | "course";
type PendingAction =
  | { kind: "grant"; input: { user_id: string; role: string; scope_type: ScopeType; scope_id: string | null; reason: string }; summary: string; impact: string }
  | { kind: "revoke"; item: RoleAssignment; reason: string; summary: string; impact: string };

const roleLabels: Record<string, string> = {
  assistant: "平台助教 / 课程助教",
  course_designer: "课程设计师",
  course_publisher: "课程发布者",
  teacher: "课程教师",
};

export default function AdminRoleAssignmentsPanel() {
  const operationKeys = useRef<AdminOperationKeyCache>(new Map());
  const listRequestVersion = useRef(0);
  const searchRequestVersion = useRef(0);
  const { canWrite, viewportReady, isNarrow } = useAdminWriteGate();
  const [items, setItems] = useState<RoleAssignment[]>([]);
  const [courses, setCourses] = useState<CourseScopeOption[]>([]);
  const [targets, setTargets] = useState<RoleAssignmentTarget[]>([]);
  const [query, setQuery] = useState("");
  const [targetId, setTargetId] = useState("");
  const [scopeType, setScopeType] = useState<ScopeType>("platform");
  const [scopeId, setScopeId] = useState("");
  const [role, setRole] = useState("");
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"active" | "revoked" | "all">("active");
  const [scopeFilter, setScopeFilter] = useState<"all" | RoleAssignment["scope_type"]>("all");
  const [scopeFilterId, setScopeFilterId] = useState("");
  const [limit, setLimit] = useState(50);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [notice, setNotice] = useState("正在读取授权记录…");
  const [noticeIsError, setNoticeIsError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [searchState, setSearchState] = useState<"idle" | "loading" | "results" | "empty" | "error">("idle");
  const [revokeReasons, setRevokeReasons] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<PendingAction | null>(null);
  const roles = scopeType === "platform"
    ? [["assistant", "平台助教"], ["course_designer", "课程设计师"], ["course_publisher", "课程发布者"]]
    : [["teacher", "课程教师"], ["assistant", "课程助教"], ["course_designer", "课程设计师"], ["course_publisher", "课程发布者"]];

  const load = useCallback(async (cursor?: string, append = false) => {
    const requestVersion = ++listRequestVersion.current;
    setListLoading(true);
    try {
      const next = await listRoleAssignments(
        status,
        scopeFilter === "all" ? undefined : scopeFilter,
        scopeFilter === "course" ? scopeFilterId || undefined : undefined,
        { limit, cursor },
      );
      if (requestVersion !== listRequestVersion.current) return false;
      setItems((current) => append ? [...current, ...next.items] : next.items);
      setNextCursor(next.nextCursor);
      setHasMore(next.hasMore);
      setNotice("");
      setNoticeIsError(false);
      return true;
    } catch (error) {
      if (requestVersion === listRequestVersion.current) {
        setNotice(explain(error));
        setNoticeIsError(true);
      }
      return false;
    } finally {
      if (requestVersion === listRequestVersion.current) setListLoading(false);
    }
  }, [status, scopeFilter, scopeFilterId, limit]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    let active = true;
    listRoleAssignmentCourses().then((next) => { if (active) setCourses(next); }).catch((error) => {
      if (active) { setNotice(explain(error)); setNoticeIsError(true); }
    });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const requestVersion = ++searchRequestVersion.current;
    const cleanQuery = query.trim();
    if (cleanQuery.length < 3) return;
    const timer = window.setTimeout(() => {
      setSearchState("loading");
      searchRoleAssignmentTargets(cleanQuery)
        .then((next) => {
          if (requestVersion !== searchRequestVersion.current) return;
          setTargets(next);
          setTargetId("");
          setSearchState(next.length ? "results" : "empty");
        })
        .catch(() => {
          if (requestVersion === searchRequestVersion.current) setSearchState("error");
        });
    }, 250);
    return () => { window.clearTimeout(timer); };
  }, [query]);
  useEffect(() => {
    if (canWrite) return;
    const timer = window.setTimeout(() => setPending(null), 0);
    return () => window.clearTimeout(timer);
  }, [canWrite]);

  function requestGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWrite || !targetId || !role || reason.trim().length < 8 || (scopeType === "course" && !scopeId)) return;
    const target = targets.find((item) => item.id === targetId);
    const course = courses.find((item) => item.id === scopeId);
    const cleanReason = reason.trim();
    const input = { user_id: targetId, role, scope_type: scopeType, scope_id: scopeType === "course" ? scopeId : null, reason: cleanReason };
    const targetLabel = target ? `${target.display_name} · ${target.email}` : targetId;
    setPending({
      kind: "grant",
      input,
      summary: `将向 ${targetLabel} 授予“${roleLabels[role] ?? role}”，范围为${scopeType === "platform" ? "平台工作区" : `课程「${course?.title ?? scopeId}」`}。`,
      impact: "授权立即生效并留下审计记录；仅授予该 Scope，不授予管理员读取教材正文或学生私聊的权限。",
    });
  }

  function requestRevoke(item: RoleAssignment, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const revokeReason = revokeReasons[item.id]?.trim() ?? "";
    if (!canWrite || revokeReason.length < 8 || item.status !== "active") return;
    const scope = item.scope_type === "platform" ? "平台工作区" : item.scope_type === "course"
      ? `课程「${courses.find((course) => course.id === item.scope_id)?.title ?? item.scope_id}」`
      : `班级 ${item.scope_id}`;
    setPending({
      kind: "revoke", item, reason: revokeReason,
      summary: `撤销 ${item.user_display_name} 的“${roleLabels[item.role] ?? item.role}”授权（${scope}，当前版本 v${item.version}）。`,
      impact: "该授权将失效；后续请求会按服务端最新 Scope 重新鉴权。其他独立课程成员/任课关系不会由此自动修改。",
    });
  }

  async function confirmPending() {
    if (!pending || !canWrite || busy) return;
    setBusy(true);
    try {
      let receipt: string;
      if (pending.kind === "grant") {
        const { input } = pending;
        const result = await grantRoleAssignment(input, adminOperationKey(operationKeys.current, "grant", input));
        clearAdminOperationKey(operationKeys.current, "grant");
        setReason("");
        receipt = `授权已生效：记录 ${result.id} · v${result.version} · ${result.status}。`;
      } else {
        const { item, reason: revokeReason } = pending;
        const input = { version: item.version, reason: revokeReason };
        const operation = `revoke:${item.id}`;
        const result = await revokeRoleAssignment(item.id, item.version, revokeReason, adminOperationKey(operationKeys.current, operation, input));
        clearAdminOperationKey(operationKeys.current, operation);
        setRevokeReasons((current) => ({ ...current, [item.id]: "" }));
        receipt = `授权已撤销：记录 ${result.id} · v${result.version} · ${result.status}。后续请求按最新 Scope 重新鉴权。`;
      }
      setPending(null);
      await load();
      setNotice(receipt);
      setNoticeIsError(false);
    } catch (error) {
      setPending(null);
      const refreshed = await load();
      setNotice(`${conflictText(error)}${refreshed ? " 当前列表已刷新；请核对服务端状态后再继续。" : " 刷新失败，请先重试刷新。"}`);
      setNoticeIsError(true);
    } finally { setBusy(false); }
  }

  return <section className="data-panel">
    <div className="panel-heading"><div><h2>身份与授权治理</h2><p>仅管理授权元数据，不授予管理员课程正文或学生私聊读取权限。</p></div><button className="secondary-button" type="button" onClick={() => void load()} disabled={listLoading}>刷新</button></div>
    {notice && <p className="status-banner" role={noticeIsError ? "alert" : "status"}>{notice}</p>}
    {viewportReady && isNarrow && <p className="status-banner" role="status">窄屏只读：为避免误授予或撤销高影响权限，请使用宽屏完成治理操作；当前仍可查看和筛选记录。</p>}
    {canWrite ? <form className="stack-form" onSubmit={requestGrant}>
      <h3>授予授权</h3>
      <label>查找同机构账号（姓名或邮箱至少 3 个字符）<input value={query} onChange={(event) => { setQuery(event.target.value); setTargetId(""); setTargets([]); setSearchState("idle"); }} autoComplete="off" /></label>
      {searchState === "loading" && <small role="status">正在搜索同机构账号…</small>}
      {searchState === "empty" && <small role="status">没有找到匹配的同机构账号；请核对姓名或邮箱。</small>}
      {searchState === "error" && <small role="alert">账号搜索失败，请修改关键词或稍后重试。</small>}
      <label>授权对象<select value={targetId} onChange={(event) => setTargetId(event.target.value)} required><option value="">选择账号</option>{targets.map((target) => <option key={target.id} value={target.id}>{target.display_name} · {target.email}</option>)}</select></label>
      <label>授权范围<select value={scopeType} onChange={(event) => { const next = event.target.value as ScopeType; setScopeType(next); setScopeId(""); setRole(""); }}>{[["platform", "平台工作区"], ["course", "单门课程"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      {scopeType === "course" && <label>课程 Scope<select value={scopeId} onChange={(event) => setScopeId(event.target.value)} required><option value="">选择同机构课程</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title} · {course.term}</option>)}</select></label>}
      <label>角色<select value={role} onChange={(event) => setRole(event.target.value)} required><option value="">选择角色</option>{roles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>授权理由（必填，至少 8 个字符）<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={8} maxLength={500} required /></label>
      <button className="primary-button" type="submit" disabled={busy || !targetId || !role || reason.trim().length < 8 || (scopeType === "course" && !scopeId)}>检查并复核授权</button>
      <small>提交前会再次展示对象、角色、Scope 和理由；平台角色仅开放助教、课程设计和发布工作区。</small>
    </form> : !viewportReady && <p className="status-banner" role="status">正在确认屏幕尺寸；写操作暂不可用。</p>}
    <div className="panel-heading"><h3>授权记录</h3><div className="admin-job-panel-actions">
      <label>状态<select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option value="active">有效</option><option value="revoked">已撤销</option><option value="all">全部</option></select></label>
      <label>Scope<select value={scopeFilter} onChange={(event) => { setScopeFilter(event.target.value as typeof scopeFilter); setScopeFilterId(""); }}><option value="all">全部 Scope</option><option value="platform">平台</option><option value="course">课程</option><option value="class">班级历史</option></select></label>
      {scopeFilter === "course" && <label>课程<select value={scopeFilterId} onChange={(event) => setScopeFilterId(event.target.value)}><option value="">全部课程</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title} · {course.term}</option>)}</select></label>}
      <label>每页<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option><option value={200}>200</option></select></label>
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={listLoading}>刷新</button>
    </div></div>
    <p className="empty-state">可按状态、Scope 和每页条数逐页读取；已加载 {items.length} 条{hasMore ? "，还有更多记录" : "，没有更多记录"}。</p>
    {listLoading ? <p className="status-banner" role="status">正在读取机构授权记录…</p> : items.length ? items.map((item) => <article className="question-card" key={item.id}>
      <div><strong>{item.user_display_name} · {roleLabels[item.role] ?? item.role}</strong><small>{item.user_email} · {item.scope_type === "platform" ? "平台" : item.scope_type === "course" ? `课程：${courses.find((course) => course.id === item.scope_id)?.title ?? item.scope_id}` : `班级：${item.scope_id}`} · v{item.version}</small><small>状态：{item.status} · 授予人：{item.granted_by ?? "—"} · 更新：{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
      {item.status === "active" && canWrite && <details><summary>撤销授权</summary><form className="stack-form" onSubmit={(event) => requestRevoke(item, event)}><label>撤销理由（必填，至少 8 个字符）<textarea value={revokeReasons[item.id] ?? ""} onChange={(event) => setRevokeReasons((current) => ({ ...current, [item.id]: event.target.value }))} minLength={8} maxLength={500} required /></label><button className="secondary-button" type="submit" disabled={busy || (revokeReasons[item.id]?.trim().length ?? 0) < 8}>复核后撤销</button></form></details>}
    </article>) : !notice && !listLoading && <p className="empty-state">当前筛选下没有授权记录。</p>}
    {hasMore && nextCursor && <button className="secondary-button" type="button" disabled={listLoading} onClick={() => void load(nextCursor, true)}>{listLoading ? "正在读取…" : "加载更多授权记录"}</button>}
    <AdminConfirmationDialog
      open={Boolean(pending)}
      title={pending?.kind === "grant" ? "复核授权变更" : "复核撤销授权"}
      summary={pending?.summary ?? ""}
      impact={pending?.impact ?? ""}
      reason={pending?.kind === "grant" ? pending.input.reason : pending?.reason ?? ""}
      confirmLabel={pending?.kind === "grant" ? "确认授予" : "确认撤销"}
      busy={busy}
      onConfirm={() => void confirmPending()}
      onCancel={() => setPending(null)}
    />
  </section>;
}
