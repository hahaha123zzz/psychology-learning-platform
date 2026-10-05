"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "../lib/api";

type DeletionStatus = {
  request_id: string;
  status: "queued" | "running" | "failed" | "completed_with_retention";
  processed_counts: Record<string, number>;
  retained_categories: string[];
  requested_at: string;
  completed_at: string | null;
  attempt_count: number;
  retryable: boolean;
  last_error_code: string | null;
};

const categoryLabels: Record<string, string> = {
  chat_turns: "对话内容",
  chat_sessions: "对话会话",
  learning_episodes: "学习片段",
  teaching_sessions: "教学会话",
  learning_tasks: "学习任务",
  learning_sessions: "学习会话",
  case_sessions: "案例练习记录",
  mini_lab_sessions: "实验练习记录",
  intervention_runs: "教师干预执行记录",
  teacher_observations: "教师观察记录",
  review_tasks: "复习任务",
  wrong_answer_traces: "错题追踪记录",
  question_quality_feedback: "题目反馈",
  learning_qualifications: "学习事件审核记录",
  learning_events: "学习事件",
  learning_evidences: "学习证据",
  mastery_states: "掌握状态",
  evidence_tickets: "临时教材引用凭证",
  memory_items: "个人记忆条目",
  user_preferences: "个人偏好",
  notifications: "站内通知",
  course_memberships: "课程成员关系",
  class_memberships: "班级成员关系",
  role_assignments: "课程/平台角色授权",
  auth_sessions: "认证会话",
  idempotency_records: "幂等请求记录",
  login_rate_limit_keys: "登录安全缓存项",
  detached_model_usage_records: "已解除身份关联的模型用量记录",
};

export default function PrivacyDeletionStatusLookup() {
  const [requestId, setRequestId] = useState("");
  const [credential, setCredential] = useState("");
  const [status, setStatus] = useState<DeletionStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setStatus(null);
    setBusy(true);
    try {
      const result = await api<DeletionStatus>("/privacy/deletion-status", {
        method: "POST",
        body: JSON.stringify({ request_id: requestId.trim(), status_credential: credential.trim() }),
      });
      setStatus(result);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "查询失败，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    setMessage("");
    setBusy(true);
    try {
      const result = await api<DeletionStatus>("/privacy/deletion-status/retry", {
        method: "POST",
        body: JSON.stringify({ request_id: requestId.trim(), status_credential: credential.trim() }),
      });
      setStatus(result);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "重试未完成，请保留凭证并稍后再试。");
    } finally {
      setBusy(false);
    }
  }

  const statusLabel: Record<DeletionStatus["status"], string> = {
    queued: "等待处理",
    running: "正在处理",
    failed: "处理失败，可按状态重试",
    completed_with_retention: "已完成部分删除，保留类别仍待机构规则处理",
  };

  return (
    <main className="functional-app">
      <header className="app-header">
        <Link href="/">实验心理学智能学习平台</Link>
        <strong>隐私删除状态核验</strong>
      </header>
      <section className="functional-main">
        <div className="section-title">
          <div>
            <p className="eyebrow">无需登录；使用提交前保存的回执编号和短期凭证核验</p>
            <h1>删除状态核验</h1>
            <p>凭证有效期为 30 天。请勿转发或公开分享；系统仅存储其哈希，不会恢复账号访问权限。若工作单可重试，此页可安全重派发。</p>
          </div>
        </div>
        <form className="data-panel" onSubmit={lookup}>
          <label>
            回执编号
            <input value={requestId} onChange={(event) => setRequestId(event.target.value)} minLength={26} maxLength={26} required />
          </label>
          <label>
            查询凭证
            <input value={credential} onChange={(event) => setCredential(event.target.value)} minLength={43} maxLength={43} required autoComplete="off" />
          </label>
          <button type="submit" disabled={busy}>{busy ? "正在核验…" : "核验删除状态"}</button>
        </form>
        {message && <p className="status-banner" role="alert">{message}</p>}
        {status && (
          <section className="data-panel" aria-live="polite">
            <h2>删除处理回执</h2>
            <p>状态：{statusLabel[status.status]}</p>
            <p>回执编号：{status.request_id}</p>
            <p>请求时间：{new Date(status.requested_at).toLocaleString()}</p>
            {status.completed_at && <p>完成时间：{new Date(status.completed_at).toLocaleString()}</p>}
            {status.last_error_code && <p>安全错误代码：{status.last_error_code}</p>}
            <p>已执行尝试：{status.attempt_count}</p>
            {status.status === "completed_with_retention" ? (
              <>
                <h3>处理数量（删除、撤销或解除关联）</h3>
                <ul>{Object.entries(status.processed_counts).map(([key, count]) => <li key={key}>{categoryLabels[key] ?? key}：{count}</li>)}</ul>
                <h3>保留边界</h3>
                <ul>{status.retained_categories.map((item) => <li key={item}>{item}</li>)}</ul>
              </>
            ) : <p>处理计数会在任务完成后提供；当前状态不代表删除已经完成。</p>}
            {status.retryable && (
              <button type="button" disabled={busy} onClick={() => void retry()}>
                {busy ? "正在重试…" : "重试删除工作单"}
              </button>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
