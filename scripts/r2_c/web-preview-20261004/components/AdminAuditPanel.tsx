"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import { listAdminAuditLogs, type AdminAuditLog } from "../lib/admin-api";

const explain = (reason: unknown) => reason instanceof ApiError
  ? reason.message
  : "无法读取机构范围内的审计记录，请稍后重试。";

export default function AdminAuditPanel() {
  const [items, setItems] = useState<AdminAuditLog[]>([]);
  const [courseInput, setCourseInput] = useState("");
  const [actionInput, setActionInput] = useState("");
  const [filters, setFilters] = useState<{ course_id?: string; action?: string }>({});
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [limit, setLimit] = useState(50);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const requestVersion = useRef(0);
  const [notice, setNotice] = useState("");

  const fetchLogs = useCallback(async (cursor?: string, append = false) => {
    const currentRequest = ++requestVersion.current;
    setLoading(true);
    try {
      const page = await listAdminAuditLogs({ ...filters, limit, cursor });
      if (currentRequest !== requestVersion.current) return false;
      setItems((current) => append ? [...current, ...page.items] : page.items);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
      setNotice("");
      return true;
    } catch (error) {
      if (currentRequest === requestVersion.current) setNotice(explain(error));
      return false;
    } finally {
      if (currentRequest === requestVersion.current) setLoading(false);
    }
  }, [filters, limit]);

  useEffect(() => { void fetchLogs(); }, [fetchLogs, refreshVersion]);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({ course_id: courseInput.trim() || undefined, action: actionInput.trim() || undefined });
  }

  return <section className="data-panel">
    <div className="panel-heading">
      <div><h2>治理操作审计</h2><p>仅查询服务端按当前机构 Scope 过滤后的最小操作元数据；不展示正文、学生答案或私聊。</p></div>
      <div className="admin-job-panel-actions">
        <label>每页<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option><option value={200}>200</option></select></label>
        <button className="secondary-button" type="button" onClick={() => setRefreshVersion((value) => value + 1)} disabled={loading}>刷新</button>
      </div>
    </div>
    <form className="stack-form" onSubmit={submitFilters}>
      <label>课程 ID（精确筛选）<input value={courseInput} onChange={(event) => setCourseInput(event.target.value)} maxLength={26} /></label>
      <label>操作类型（精确筛选）<input value={actionInput} onChange={(event) => setActionInput(event.target.value)} maxLength={100} /></label>
      <button className="secondary-button" type="submit">应用筛选</button>
    </form>
    {loading ? <p className="status-banner" role="status">正在读取当前机构 Scope 内的审计记录…</p> : notice && <p className="status-banner" role="alert">{notice}</p>}
    {!loading && !notice && <p className="empty-state">已加载 {items.length} 条{hasMore ? "，还有更多记录" : "，没有更多记录"}。游标翻页可继续检查历史范围。</p>}
    {!loading && !notice && items.length ? items.map((item) => <article className="question-card" key={item.id}>
      <div><strong>{item.action}</strong><small>{item.resource_type} · 资源 {item.resource_id.slice(-6)} · 操作者 {item.actor_id.slice(-6)}</small><small>{item.course_id ? `课程 Scope：${item.course_id}` : "机构级治理操作"} · {new Date(item.created_at).toLocaleString("zh-CN")}</small></div>
    </article>) : !loading && !notice && <p className="empty-state">当前机构范围和筛选条件下没有审计记录。</p>}
    {hasMore && nextCursor && <button className="secondary-button" type="button" disabled={loading} onClick={() => void fetchLogs(nextCursor, true)}>{loading ? "正在读取…" : "加载更多审计记录"}</button>}
  </section>;
}
