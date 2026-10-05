"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { loadAdminGovernanceOverview, type AdminGovernanceOverview } from "../lib/admin-governance";

const explain = (error: unknown) => error instanceof ApiError
  ? error.message
  : "无法读取管理员运行概览，请检查 API 后重试。";

export default function AdminOverviewPanel() {
  const requestVersion = useRef(0);
  const [overview, setOverview] = useState<AdminGovernanceOverview | null>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const currentRequest = ++requestVersion.current;
    setLoading(true);
    setNotice("");
    try {
      const result = await loadAdminGovernanceOverview();
      if (currentRequest === requestVersion.current) setOverview(result);
    } catch (error) {
      if (currentRequest === requestVersion.current) {
        setOverview(null);
        setNotice(explain(error));
      }
    } finally {
      if (currentRequest === requestVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const scheduledLoad = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(scheduledLoad);
  }, [load]);

  return <section className="data-panel">
    <div className="panel-heading">
      <div><h2>运行概览</h2><p>实时显示服务状态及同机构汇总；工作区仍按各自课程 Scope 授权。</p></div>
      <button className="secondary-button" type="button" onClick={() => void load()} disabled={loading}>
        {loading ? "读取中…" : "刷新"}
      </button>
    </div>
    {loading && <p className="status-banner" role="status">正在读取管理员运行概览…</p>}
    {!loading && notice && <div><p className="status-banner" role="alert">{notice}</p><button className="secondary-button" type="button" onClick={() => void load()}>重试</button></div>}
    {!loading && overview && <>
      <dl className="data-details">
        <dt>API</dt><dd>{overview.apiStatus === "ok" ? "正常" : "降级"}</dd>
        <dt>数据库</dt><dd>{overview.databaseStatus === "ok" ? "正常" : `状态：${overview.databaseStatus}`}</dd>
        <dt>Redis</dt><dd>{overview.redisStatus === "ok" ? "正常" : `状态：${overview.redisStatus}`}</dd>
        <dt>同机构账号</dt><dd>{overview.organizationUserCount}</dd>
        <dt>进行中测评</dt><dd>{overview.inProgressAttempts}</dd>
        <dt>更新时间</dt><dd>{overview.serverTime ? new Date(overview.serverTime).toLocaleString("zh-CN") : "暂不可用"}</dd>
      </dl>
      {overview.organizationUserCount === 0 && overview.inProgressAttempts === 0 && <p className="empty-state">当前机构暂无账号或进行中的测评；服务状态来自实时接口。</p>}
    </>}
  </section>;
}
