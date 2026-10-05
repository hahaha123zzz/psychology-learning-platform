"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";
import { createDeletionRecoveryMaterial } from "../lib/privacy-deletion";
import StudentPreferencesPanel from "./StudentPreferencesPanel";
import StudentNotificationsPanel from "./StudentNotificationsPanel";

const fail = (error: unknown) =>
  error instanceof ApiError ? error.message : "请求失败。";

type DeletionReceipt = {
  request_id: string;
  status: "queued" | "running" | "failed" | "completed_with_retention";
  processed_counts: Record<string, number>;
  retained_categories: string[];
  note: string;
  attempt_count: number;
  retryable: boolean;
  last_error_code: string | null;
  status_credential: string;
  status_credential_expires_at: string;
};

const deletionCategoryLabels: Record<string, string> = {
  chat_turns: "对话内容",
  chat_sessions: "对话会话",
  learning_episodes: "学习片段",
  teaching_sessions: "教学会话",
  learning_tasks: "学习任务",
  learning_sessions: "旧版学习会话",
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

export default function StudentProfile() {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [notice, setNotice] = useState("");
  const [deletionReceipt, setDeletionReceipt] = useState<DeletionReceipt | null>(null);
  const [deletionChallenge, setDeletionChallenge] = useState<{
    request_id: string;
    status_credential: string;
  } | null>(null);
  const [recoverySaved, setRecoverySaved] = useState(false);

  const load = () =>
    Promise.all([
      api<Record<string, unknown>>("/me/memory"),
      api<Record<string, unknown>[]>("/me/memory/items?limit=20"),
    ])
      .then(([nextSummary, nextItems]) => {
        setSummary(nextSummary);
        setItems(nextItems);
      })
      .catch((error) => setNotice(fail(error)));

  useEffect(() => {
    void load();
  }, []);

  async function erase() {
    const confirmation =
      "此操作将立即停用并去标识化账号，排队清除个人学习数据；正式答卷、成绩与审计按明确保留边界留存。是否继续准备删除请求？";
    if (!confirm(confirmation)) return;
    setDeletionChallenge(createDeletionRecoveryMaterial());
    setRecoverySaved(false);
  }

  async function submitDeletion() {
    if (!deletionChallenge || !recoverySaved) return;
    try {
      const receipt = await api<DeletionReceipt>("/me/privacy/delete-request", {
        method: "POST",
        body: JSON.stringify(deletionChallenge),
      });
      setSummary(null);
      setItems([]);
      setDeletionReceipt(receipt);
    } catch (error) {
      setNotice(
        `提交结果暂未确认。账号可能已经停用；请保留恢复信息并在状态核验页查询或重试。${fail(error)}`,
      );
    }
  }

  return (
    <main className="functional-app">
      <header className="app-header">
        <Link href="/" className="app-brand">
          <Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台
        </Link>
        <Link href="/student">学习空间</Link>
        <strong>学习记忆与隐私</strong>
      </header>
      <section className="functional-main">
        <div className="section-title">
          <div>
            <p className="eyebrow">来源与时效由服务端维护</p>
            <h1>学习记忆与隐私</h1>
            <p>这里展示服务端允许本人查看的记忆摘要和条目，不展示内部模型 Prompt。</p>
          </div>
        </div>
        {notice && <p className="status-banner">{notice}</p>}
        {deletionReceipt ? (
          <section className="data-panel" aria-live="polite">
            <h2>删除处理回执</h2>
            <p>状态：{deletionReceipt.status}</p>
            <p>回执编号：{deletionReceipt.request_id}</p>
            <p>查询凭证（请在 30 天内保存并核验）：</p>
            <p><code>{deletionReceipt.status_credential}</code></p>
            <p>有效期至：{new Date(deletionReceipt.status_credential_expires_at).toLocaleString()}</p>
            <p><Link href="/privacy/deletion-status">打开删除状态核验页</Link></p>
            <p>{deletionReceipt.note}</p>
            {deletionReceipt.status === "completed_with_retention" ? (
              <>
                <h3>处理数量（删除、撤销或解除关联）</h3>
                <ul>
                  {Object.entries(deletionReceipt.processed_counts).map(([category, count]) => (
                    <li key={category}>{deletionCategoryLabels[category] ?? category}：{count}</li>
                  ))}
                </ul>
                <h3>保留边界</h3>
                <ul>{deletionReceipt.retained_categories.map((category) => <li key={category}>{category}</li>)}</ul>
              </>
            ) : <p>个人学习数据仍在处理；当前回执不代表删除已经完成。</p>}
            <p>账号已退出；为保护隐私，本页不再展示刚刚删除的个人内容。</p>
          </section>
        ) : (
          <>
            <StudentPreferencesPanel />
            <StudentNotificationsPanel />
            <div className="data-grid">
              <section className="data-panel">
                <h2>记忆摘要</h2>
                {summary ? (
                  <pre className="json-summary">{JSON.stringify(summary, null, 2)}</pre>
                ) : (
                  <p className="empty-state">正在读取记忆摘要…</p>
                )}
              </section>
              <section className="data-panel">
                <h2>删除请求</h2>
                <p className="empty-state">
                  删除请求会立即停用并去标识化账号；个人学习数据完成后提供处理计数。正式答卷、成绩与审计按保留边界留存。
                </p>
                <button className="secondary-button" onClick={() => void erase()}>
                  准备隐私删除请求
                </button>
                {deletionChallenge && (
                  <div className="data-panel" aria-live="polite">
                    <h3>提交前先保存恢复信息</h3>
                    <p>回执编号：<code>{deletionChallenge.request_id}</code></p>
                    <p>查询凭证：<code>{deletionChallenge.status_credential}</code></p>
                    <label>
                      <input
                        type="checkbox"
                        checked={recoverySaved}
                        onChange={(event) => setRecoverySaved(event.target.checked)}
                      />
                      我已将编号和凭证保存到安全位置
                    </label>
                    <button disabled={!recoverySaved} onClick={() => void submitDeletion()}>
                      确认并提交删除
                    </button>
                  </div>
                )}
              </section>
            </div>
            <section className="data-panel">
              <h2>记忆条目</h2>
              {items.length ? (
                items.map((item, index) => (
                  <pre className="memory-item" key={String(item.id ?? index)}>
                    {JSON.stringify(item, null, 2)}
                  </pre>
                ))
              ) : (
                <p className="empty-state">暂无可展示的记忆条目。</p>
              )}
            </section>
          </>
        )}
      </section>
    </main>
  );
}
