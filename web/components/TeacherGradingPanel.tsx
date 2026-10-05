"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, idempotencyKey } from "../lib/api";

type QueueItem = {
  attempt_id: string;
  assessment_id: string;
  assessment_title: string;
  student_display_name: string;
  submitted_at: string | null;
  grading_status: string | null;
};
type GradeDecision = {
  decision_id: string;
  decision_version: number;
  grader_id: string;
  points_awarded: number;
  rationale: string;
  override_reason: string | null;
  created_at: string;
};
type GradeItem = {
  question_version_id: string;
  order_no: number;
  type: string;
  stem: string;
  response: Record<string, unknown> | null;
  rubric: string | null;
  max_points: number;
  gradable: boolean;
  objective_points_earned: number | null;
  decisions: GradeDecision[];
};
type GradingDetail = {
  attempt_id: string;
  assessment_title: string;
  student_display_name: string | null;
  submitted_at: string | null;
  grading_status: string | null;
  score_version: number;
  score_record: { score: number; max_score: number; released_at: string; override_reason: string | null } | null;
  items: GradeItem[];
};
type DraftGrade = { points_awarded: string; rationale: string };

const message = (error: unknown) => error instanceof ApiError ? error.message : "评分请求未完成，请检查服务后重试。";

export default function TeacherGradingPanel({ courseId }: { courseId: string }) {
  const [includeGraded, setIncludeGraded] = useState(false);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<GradingDetail | null>(null);
  const [drafts, setDrafts] = useState<Record<string, DraftGrade>>({});
  const [overrideReason, setOverrideReason] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const pendingKey = useRef<string | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const items = await api<QueueItem[]>(`/courses/${courseId}/grading-queue?include_graded=${includeGraded}`);
      setQueue(items);
      setNotice("");
    } catch (error) {
      setNotice(message(error));
    }
  }, [courseId, includeGraded]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadQueue(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadQueue]);

  async function open(item: QueueItem) {
    setLoading(true);
    setSelectedId(item.attempt_id);
    setDetail(null);
    try {
      const next = await api<GradingDetail>(`/teacher/attempts/${item.attempt_id}/grading`);
      setDetail(next);
      setDrafts(Object.fromEntries(next.items.filter((entry) => entry.gradable).map((entry) => {
        const previous = entry.decisions[entry.decisions.length - 1];
        return [entry.question_version_id, {
          points_awarded: previous ? String(previous.points_awarded) : "",
          rationale: previous?.rationale ?? "",
        }];
      })));
      setOverrideReason("");
      pendingKey.current = null;
      setNotice("");
    } catch (error) {
      setNotice(message(error));
    } finally {
      setLoading(false);
    }
  }

  function updateDraft(questionId: string, field: keyof DraftGrade, value: string) {
    pendingKey.current = null;
    setDrafts((current) => ({
      ...current,
      [questionId]: { ...current[questionId], [field]: value },
    }));
  }

  async function saveGrade(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const gradable = detail.items.filter((item) => item.gradable);
    const invalid = gradable.find((item) => {
      const draft = drafts[item.question_version_id];
      const points = Number(draft?.points_awarded);
      return !draft?.points_awarded.trim() || !Number.isFinite(points) || points < 0 || points > item.max_points || !draft?.rationale.trim();
    });
    if (invalid) {
      setNotice(`第 ${invalid.order_no} 题需填写有效分数和评分理由，分数范围为 0–${invalid.max_points}。`);
      return;
    }
    if (detail.score_version > 0 && !overrideReason.trim()) {
      setNotice("覆盖已发布成绩时必须填写复核理由。");
      return;
    }
    setSaving(true);
    const key = pendingKey.current ?? idempotencyKey();
    pendingKey.current = key;
    try {
      await api(`/teacher/attempts/${detail.attempt_id}/grading`, {
        method: "PUT",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          expected_score_version: detail.score_version,
          override_reason: detail.score_version > 0 ? overrideReason.trim() : null,
          items: gradable.map((item) => ({
            question_version_id: item.question_version_id,
            points_awarded: Number(drafts[item.question_version_id].points_awarded),
            rationale: drafts[item.question_version_id].rationale.trim(),
          })),
        }),
      });
      pendingKey.current = null;
      setNotice(detail.score_version > 0 ? "复核后的成绩已发布，旧评分记录仍保留。" : "评分已保存并发布为正式成绩。");
      await loadQueue();
      const next = await api<GradingDetail>(`/teacher/attempts/${detail.attempt_id}/grading`);
      setDetail(next);
      setDrafts(Object.fromEntries(next.items.filter((entry) => entry.gradable).map((entry) => {
        const previous = entry.decisions[entry.decisions.length - 1];
        return [entry.question_version_id, { points_awarded: String(previous.points_awarded), rationale: previous.rationale }];
      })));
      setOverrideReason("");
    } catch (error) {
      setNotice(message(error));
    } finally {
      setSaving(false);
    }
  }

  return <section className="grading-panel support-panel" aria-labelledby="grading-heading">
    <div className="panel-heading"><h2 id="grading-heading">主观题评分与复核</h2><button className="secondary-button" type="button" aria-pressed={includeGraded} onClick={() => setIncludeGraded((value) => !value)}>{includeGraded ? "查看待评分" : "查看已评分/复核"}</button></div>
    {notice && <p className="status-banner" role="status">{notice}</p>}
    <div className="grading-workspace">
      <aside className="grading-queue" aria-label="评分队列">
        <h3>{includeGraded ? "已评分记录" : "待评分提交"}</h3>
        {queue.length ? queue.map((item) => <button type="button" className={selectedId === item.attempt_id ? "grading-queue-item active" : "grading-queue-item"} key={item.attempt_id} aria-current={selectedId === item.attempt_id ? "true" : undefined} onClick={() => void open(item)}>
          <strong>{item.student_display_name}</strong><span>{item.assessment_title}</span><small>{item.submitted_at ? new Date(item.submitted_at).toLocaleString("zh-CN") : "提交时间未知"}</small>
        </button>) : <p className="empty-state">{includeGraded ? "暂无可复核的主观题成绩。" : "当前没有待评分提交。"}</p>}
      </aside>
      <div className="grading-response" aria-live="polite">
        {loading && <p>正在读取评分材料…</p>}
        {!loading && !detail && <p className="empty-state">选择一份提交后查看学生作答与评分标准。</p>}
        {detail && <>
          <div className="grading-student-heading"><p className="eyebrow">{detail.assessment_title}</p><h3>{detail.student_display_name ?? "学生"}</h3><small>提交时间：{detail.submitted_at ? new Date(detail.submitted_at).toLocaleString("zh-CN") : "未知"}</small></div>
          <details className="grading-ai-note"><summary>AI 评分建议（默认折叠）</summary><p>当前未配置获准处理学生作答的评分模型，因此不生成候选建议，也不会把学生答案发送到外部服务。请依据右侧 Rubric 独立评分。</p></details>
          {detail.items.map((item) => <article className="grading-question" key={item.question_version_id}>
            <h4>{item.order_no}. {item.stem}</h4>
            <p className="grading-label">学生作答</p><pre>{item.response ? JSON.stringify(item.response, null, 2) : "未提交作答"}</pre>
            {item.rubric && <><p className="grading-label">评分 Rubric · 满分 {item.max_points}</p><p>{item.rubric}</p></>}
            {!item.gradable && <p>客观题已由服务端评分：{item.objective_points_earned ?? 0}/{item.max_points} 分</p>}
            {item.decisions.length > 0 && <details><summary>历史教师决定（{item.decisions.length}）</summary>{item.decisions.map((decision) => <p key={decision.decision_id}>第 {decision.decision_version} 版：{decision.points_awarded}/{item.max_points} 分 · {decision.rationale}{decision.override_reason ? ` · 覆盖理由：${decision.override_reason}` : ""}</p>)}</details>}
          </article>)}
        </>}
      </div>
      <div className="grading-controls">
        {detail && <form className="grading-form" onSubmit={(event) => void saveGrade(event)}>
          <h3>{detail.score_version > 0 ? "复核 / 覆盖成绩" : "教师评分决定"}</h3>
          {detail.score_record && <p className="score-record">正式成绩：{detail.score_record.score}/{detail.score_record.max_score} · 第 {detail.score_version} 版 · 发布于 {new Date(detail.score_record.released_at).toLocaleString("zh-CN")}</p>}
          {detail.items.filter((item) => item.gradable).map((item) => <fieldset className="grading-field" key={item.question_version_id}>
            <legend>第 {item.order_no} 题 · 0–{item.max_points} 分</legend>
            <label htmlFor={`grade-${item.question_version_id}`}>得分</label><input id={`grade-${item.question_version_id}`} type="number" min="0" max={item.max_points} step="0.25" required value={drafts[item.question_version_id]?.points_awarded ?? ""} onChange={(event) => updateDraft(item.question_version_id, "points_awarded", event.target.value)} />
            <label htmlFor={`rationale-${item.question_version_id}`}>评分理由</label><textarea id={`rationale-${item.question_version_id}`} required maxLength={5000} value={drafts[item.question_version_id]?.rationale ?? ""} onChange={(event) => updateDraft(item.question_version_id, "rationale", event.target.value)} />
          </fieldset>)}
          {detail.score_version > 0 && <label className="override-field">覆盖理由<textarea required maxLength={2000} value={overrideReason} onChange={(event) => { pendingKey.current = null; setOverrideReason(event.target.value); }} /></label>}
          <p>教师决定与 ScoreRecord 分开追加保存；已发布成绩不会被覆盖删除。</p>
          <button className="primary-button" type="submit" disabled={saving}>{saving ? "正在保存…" : detail.score_version > 0 ? "保存复核并发布新版本" : "保存评分并发布成绩"}</button>
        </form>}
      </div>
    </div>
  </section>;
}
