"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";
import { createDeletionRecoveryMaterial } from "../lib/privacy-deletion";
import StudentMiniLabPanel from "./StudentMiniLabPanel";
import StudentPreferencesPanel from "./StudentPreferencesPanel";
import StudentNotificationsPanel from "./StudentNotificationsPanel";

type Assessment = { id: string; title: string; purpose: "practice" | "formal"; availability: string; ai_policy: string; current_attempt_id?: string | null };
type Question = { question_version_id: string; order_no: number; points: number; type: string; stem: string; options?: { key: string; text: string }[] };
type AssessmentDetail = { id: string; title: string; items: Question[] };
type StartedAttempt = { attempt_id: string; answers: { question_version_id: string; response: { selected_keys?: string[]; text?: string } | null; answer_version: number; flagged: boolean }[] };
type Result = { score: number | null; grading_status: string; items: { question_version_id: string; points_earned: number | null; explanation?: string }[] };
type Review = { id: string; course_id: string; reason: string; due_at: string; version?: number; question?: { type: string; stem: string; options: { key: string; text: string }[] }; qualification_status?: string };
type GrowthKnowledge = { knowledge_point: string; state: string; evidence_count: number; state_reason: string; algorithm_version: string; next_step: string; updated_at: string };
type GrowthTabs = { knowledge: GrowthKnowledge[]; skills: { skill: string; status: string; evidence_count: number; next_step: string }[]; misconceptions: { knowledge_point: string; status: string; explanation: string; confidence: number; updated_at: string }[]; trajectory: { date: string; evidence_count: number; knowledge_points: string[] }[] };
type MemoryItem = { id: string; layer: string; kind: string; content: string; confidence: number; course_id: string | null; provenance_level: string; evidence_refs: string[]; valid_from: string | null; expires_at: string | null; review_after: string | null; needs_review: boolean; conflict_status: string; updated_at: string };
type MemorySummary = { summary: Record<string, number>; stale_hidden: number };
function message(reason: unknown): string { return reason instanceof ApiError ? reason.message : "请求未完成，请检查本地服务后重试。"; }

export function StudentPracticePage() {
  const { courseId } = useParams<{ courseId: string }>();
  const essayTimers = useRef<Record<string, number>>({});
  const answerVersions = useRef<Record<string, number>>({});
  const saveRequests = useRef<Record<string, Promise<boolean>>>({});
  const saveErrors = useRef<Record<string, boolean>>({});
  const [assessments, setAssessments] = useState<Assessment[]>([]); const [reviews, setReviews] = useState<Review[]>([]); const [reviewAnswers, setReviewAnswers] = useState<Record<string, string>>({}); const [detail, setDetail] = useState<AssessmentDetail | null>(null); const [attemptId, setAttemptId] = useState(""); const [answers, setAnswers] = useState<Record<string, string>>({}); const [flagged, setFlagged] = useState<Record<string, boolean>>({}); const [saveState, setSaveState] = useState<Record<string, "editing" | "saving" | "saved" | "error">>({}); const [result, setResult] = useState<Result | null>(null); const [notice, setNotice] = useState("正在读取练习…");
  const open = useCallback(async (assessment: Assessment) => { try { const [nextDetail, attempt] = await Promise.all([api<AssessmentDetail>(`/assessments/${assessment.id}`), api<StartedAttempt>(`/assessments/${assessment.id}/attempts`, { method: "POST" })]); const restoredAnswers: Record<string, string> = {}; const restoredVersions: Record<string, number> = {}; const restoredFlags: Record<string, boolean> = {}; for (const saved of attempt.answers) { const answer = saved.response?.selected_keys?.[0] ?? saved.response?.text; if (typeof answer === "string") restoredAnswers[saved.question_version_id] = answer; restoredVersions[saved.question_version_id] = saved.answer_version; restoredFlags[saved.question_version_id] = saved.flagged; } Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); essayTimers.current = {}; answerVersions.current = restoredVersions; saveRequests.current = {}; saveErrors.current = {}; setDetail(nextDetail); setAttemptId(attempt.attempt_id); setAnswers(restoredAnswers); setFlagged(restoredFlags); setSaveState({}); setResult(null); setNotice(""); } catch (reason) { setNotice(message(reason)); } }, []);
  const load = useCallback(async () => {
    const [assessmentResult, reviewResult] = await Promise.allSettled([
      api<Assessment[]>(`/courses/${courseId}/assessments`),
      api<Review[]>("/review-tasks?due_only=false"),
    ]);
    const errors: string[] = [];
    let nextAssessments: Assessment[] = [];
    if (assessmentResult.status === "fulfilled") {
      nextAssessments = assessmentResult.value.filter((assessment) => assessment.purpose === "practice");
      setAssessments(nextAssessments);
    } else {
      errors.push(message(assessmentResult.reason));
    }
    if (reviewResult.status === "fulfilled") {
      setReviews(reviewResult.value.filter((review) => review.course_id === courseId));
    } else {
      setReviews([]);
      errors.push(message(reviewResult.reason));
    }
    setNotice(errors.join("；"));
    const activeAttempt = nextAssessments.find(
      (assessment) => assessment.availability === "open" && assessment.current_attempt_id,
    );
    if (activeAttempt) await open(activeAttempt);
  }, [courseId, open]);
  // 此 effect 仅发起路由课程对应的外部 API 加载，状态在异步请求完成后更新。
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); }, []);
  async function completeReview(task: Review) { try { await api(`/review-tasks/${task.id}/complete`, { method: "POST" }); setReviews((items) => items.filter((item) => item.id !== task.id)); } catch (reason) { setNotice(message(reason)); } }
  async function verifyReview(task: Review) { const selected = reviewAnswers[task.id]; if (!selected || task.version === undefined) return; try { await api(`/review-tasks/${task.id}/verify`, { method: "POST", body: JSON.stringify({ version: task.version, response: { selected_keys: [selected] } }) }); setReviews((items) => items.filter((item) => item.id !== task.id)); setReviewAnswers((items) => { const next = { ...items }; delete next[task.id]; return next; }); setNotice("复习答案已提交，服务端将记录延迟保持证据。"); } catch (reason) { setNotice(message(reason)); } }
  function saveResponse(questionId: string, response: Record<string, unknown>): Promise<boolean> {
    if (!attemptId) return Promise.resolve(false);
    setSaveState((items) => ({ ...items, [questionId]: "saving" }));
    const previous = saveRequests.current[questionId] ?? Promise.resolve(true);
    const pending = previous.then(async () => {
      try {
        const saved = await api<{ answer_version: number }>(`/attempts/${attemptId}/answers/${questionId}`, { method: "PUT", body: JSON.stringify({ answer_version: answerVersions.current[questionId] ?? 1, response, client_saved_at: new Date().toISOString() }) });
        answerVersions.current[questionId] = saved.answer_version;
        saveErrors.current[questionId] = false;
        setSaveState((items) => ({ ...items, [questionId]: "saved" }));
        return true;
      } catch (reason) {
        saveErrors.current[questionId] = true;
        setNotice(message(reason));
        setSaveState((items) => ({ ...items, [questionId]: "error" }));
        return false;
      }
    });
    saveRequests.current[questionId] = pending;
    void pending.then(() => { if (saveRequests.current[questionId] === pending) delete saveRequests.current[questionId]; });
    return pending;
  }
  function save(questionId: string, selected: string) { setAnswers((items) => ({ ...items, [questionId]: selected })); void saveResponse(questionId, { selected_keys: [selected] }); }
  function queueEssaySave(questionId: string, value: string) { setAnswers((items) => ({ ...items, [questionId]: value })); setSaveState((items) => ({ ...items, [questionId]: "editing" })); const old = essayTimers.current[questionId]; if (old !== undefined) window.clearTimeout(old); essayTimers.current[questionId] = window.setTimeout(() => { delete essayTimers.current[questionId]; void saveResponse(questionId, { text: value }); }, 600); }
  function flushEssaySave(questionId: string) { const timer = essayTimers.current[questionId]; if (timer !== undefined) { window.clearTimeout(timer); delete essayTimers.current[questionId]; void saveResponse(questionId, { text: answers[questionId] ?? "" }); } }
  async function toggleFlag(questionId: string) { if (!attemptId || !answers[questionId]) return; const nextFlag = !flagged[questionId]; try { const response = await api<{ answer_version: number; flagged: boolean }>(`/attempts/${attemptId}/answers/${questionId}/flag`, { method: "PUT", body: JSON.stringify({ answer_version: answerVersions.current[questionId] ?? 1, flagged: nextFlag }) }); answerVersions.current[questionId] = response.answer_version; setFlagged((items) => ({ ...items, [questionId]: response.flagged })); } catch (reason) { setNotice(message(reason)); } }
  async function submit() {
    const timedEssaySaves = Object.entries(essayTimers.current).map(([questionId, timer]) => {
      window.clearTimeout(timer);
      delete essayTimers.current[questionId];
      return saveResponse(questionId, { text: answers[questionId] ?? "" });
    });
    const alreadySaving = Object.values(saveRequests.current);
    const saved = await Promise.all([...timedEssaySaves, ...alreadySaving]);
    if (saved.some((ok) => !ok) || Object.values(saveErrors.current).some(Boolean)) return;
    try { await api(`/attempts/${attemptId}/submit`, { method: "POST" }); setResult(await api<Result>(`/attempts/${attemptId}/result`)); } catch (reason) { setNotice(message(reason)); }
  }
  const savePending = Object.values(saveState).some((state) => state === "editing" || state === "saving");
  const saveFailed = Object.values(saveState).some((state) => state === "error");
  return <div className="student-support-page"><div className="page-heading"><div><h1>练习与复习</h1><p>练习只显示 purpose=practice；正式测评在独立 Assessment 页面中进行。</p></div></div>{notice && <p className="status-banner">{notice}</p>}{!detail ? <div className="practice-grid"><section className="support-panel"><div className="panel-heading"><h2>待复习</h2><span>{reviews.length} 项</span></div>{reviews.length ? reviews.map((review) => <article className="review-row" key={review.id}><span><strong>{review.reason}</strong><small>{review.question?.stem ?? "复习任务"} · 截止：{new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span>{review.question?.options?.length && review.version !== undefined ? <span className="review-actions"><select aria-label="选择复习答案" value={reviewAnswers[review.id] ?? ""} onChange={(event) => setReviewAnswers((items) => ({ ...items, [review.id]: event.target.value }))}><option value="">选择答案</option>{review.question.options.map((option) => <option key={option.key} value={option.key}>{option.key}. {option.text}</option>)}</select><button className="secondary-button" disabled={!reviewAnswers[review.id]} onClick={() => void verifyReview(review)}>验证并完成</button></span> : <button className="secondary-button" onClick={() => void completeReview(review)}>标记完成</button>}</article>) : <p className="empty-state">暂无待复习任务。</p>}</section><section className="support-panel"><div className="panel-heading"><h2>可参加的练习</h2><span>{assessments.length} 个</span></div><p>正式测评与练习分开；练习作答会保存进度并在提交后显示反馈。</p>{assessments.length ? assessments.map((assessment) => <article className="review-row" key={assessment.id}><span><strong>{assessment.title}</strong><small>{assessment.availability}</small></span><button className="primary-button" disabled={assessment.availability !== "open"} onClick={() => void open(assessment)}>{assessment.current_attempt_id ? "恢复练习" : assessment.availability === "open" ? "开始练习" : "暂不可参加"}</button></article>) : <p className="empty-state">当前课程没有可参加的练习。</p>}</section></div> : !result ? <section className="attempt-panel"><div className="attempt-header"><div><h2>{detail.title}</h2><p>作答将自动保存；提交后由服务端评分。</p></div><span>{Object.values(answers).filter(Boolean).length} / {detail.items.length} 已作答</span></div>{detail.items.map((item) => <article className="attempt-question" key={item.question_version_id}><strong>{item.order_no}. {item.stem}</strong>{item.type === "essay" || item.type === "short_answer" ? <label className="assessment-text-answer">文字作答<textarea aria-label={`第 ${item.order_no} 题文字作答`} maxLength={12000} rows={5} value={answers[item.question_version_id] ?? ""} onChange={(event) => queueEssaySave(item.question_version_id, event.target.value)} onBlur={() => flushEssaySave(item.question_version_id)} /></label> : item.options?.map((option) => <label key={option.key}><input type="radio" name={item.question_version_id} checked={answers[item.question_version_id] === option.key} onChange={() => void save(item.question_version_id, option.key)} />{option.key}. {option.text}</label>)}<label><input type="checkbox" checked={Boolean(flagged[item.question_version_id])} disabled={!answers[item.question_version_id] || savePending} onChange={() => void toggleFlag(item.question_version_id)} />标记此题，稍后检查</label><small role="status">{saveState[item.question_version_id] === "editing" ? "编辑中，尚未保存" : saveState[item.question_version_id] === "saving" ? "正在保存…" : saveState[item.question_version_id] === "error" ? "保存失败" : answers[item.question_version_id] ? "已保存" : "尚未作答"}</small></article>)}{saveFailed && <p role="alert">答案保存失败，请修改或重试后再提交。</p>}<div className="attempt-actions"><button className="secondary-button" onClick={() => setDetail(null)}>返回练习</button><button className="primary-button" disabled={savePending || saveFailed} onClick={() => void submit()}>提交练习</button></div></section> : <section className="attempt-panel result-panel"><Icon icon="solar:check-circle-bold" /><h2>练习完成</h2><strong>{result.score ?? "待教师评分"}</strong><p>评分状态：{result.grading_status}</p>{result.items.map((item) => <article className="result-row" key={item.question_version_id}><span>本题得分：{item.points_earned ?? "—"}</span><small>{item.explanation ?? "暂无可显示解析"}</small></article>)}<button className="secondary-button" onClick={() => { setDetail(null); setResult(null); void load(); }}>返回练习</button></section>}<StudentMiniLabPanel courseId={courseId} /></div>;
}

export function StudentGrowthPage() {
  const { courseId } = useParams<{ courseId: string }>(); const [knowledge, setKnowledge] = useState<GrowthKnowledge[]>([]); const [tabs, setTabs] = useState<GrowthTabs | null>(null); const [tab, setTab] = useState<keyof GrowthTabs>("knowledge"); const [reviews, setReviews] = useState<Review[]>([]); const [focus, setFocus] = useState<{ knowledge_point: string; state: string; state_reason: string; next_step: string } | null>(null); const [dueCount, setDueCount] = useState(0); const [notice, setNotice] = useState("正在读取成长信息…");
  useEffect(() => { Promise.all([api<{ focus: { knowledge_point: string; state: string; state_reason: string; next_step: string } | null; attention: { due_review_count: number } }>(`/student/growth/overview?course_id=${courseId}`), api<GrowthKnowledge[]>(`/student/growth/knowledge?course_id=${courseId}`), api<GrowthTabs>(`/student/growth/tabs?course_id=${courseId}`), api<Review[]>("/review-tasks?due_only=false")]).then(([overview, nextKnowledge, nextTabs, nextReviews]) => { setFocus(overview.focus); setDueCount(overview.attention.due_review_count); setKnowledge(nextKnowledge); setTabs(nextTabs); setReviews(nextReviews); setNotice(""); }).catch((reason) => setNotice(message(reason))); }, [courseId]);
  const tabLabels: Record<keyof GrowthTabs, string> = { knowledge: "知识", skills: "技能", misconceptions: "误区", trajectory: "轨迹" };
  return <div className="student-support-page"><div className="page-heading"><div><h1>成长</h1><p>根据你的学习与练习记录，查看当前掌握状态、依据和下一步行动。</p></div></div>{notice && <p className="status-banner" role="status">{notice}</p>}<section className="support-panel growth-panel"><div className="panel-heading"><h2>下一步</h2><span>{dueCount ? `${dueCount} 项到期复习` : "状态已更新"}</span></div>{focus ? <div className="growth-focus"><strong>{focus.knowledge_point}</strong><small>{focus.state} · {focus.next_step}</small><small>{focus.state_reason}</small></div> : <p className="empty-state">完成学习或测验后，这里会生成可解释的成长建议。</p>}</section><section className="support-panel growth-panel"><div className="growth-tabs" role="tablist" aria-label="成长信息类别">{(Object.keys(tabLabels) as (keyof GrowthTabs)[]).map((key) => <button type="button" className={key === tab ? "secondary-button active" : "secondary-button"} key={key} role="tab" aria-selected={key === tab} aria-controls="growth-tab-panel" id={`growth-tab-${key}`} onClick={() => setTab(key)}>{tabLabels[key]}</button>)}</div><div id="growth-tab-panel" role="tabpanel" aria-labelledby={`growth-tab-${tab}`}>{tab === "knowledge" && (knowledge.length ? knowledge.map((item) => <div className="growth-row" key={item.knowledge_point}><span><strong>{item.knowledge_point}</strong><small>{item.state} · 依据 {item.evidence_count} 条</small><small>{item.state_reason}</small><small>更新于 {new Date(item.updated_at).toLocaleDateString("zh-CN")} · 规则 {item.algorithm_version}</small></span><em>{item.next_step}</em></div>) : <p className="empty-state">当前还没有足够的学习证据。</p>)}{tab === "skills" && <p className="empty-state">当前服务端只有知识点掌握记录，没有独立技能证据；此处不会把知识点状态当作技能结论。</p>}{tab === "misconceptions" && <p className="empty-state">当前没有经确认的误区定义；待复核的学习记忆不作为误区结论展示。</p>}{tab === "trajectory" && (tabs?.trajectory.length ? tabs.trajectory.map((item) => <div className="growth-row" key={item.date}><span><strong>{item.date}</strong><small>{item.knowledge_points.length} 个知识点</small></span><em>学习证据 {item.evidence_count} 条</em></div>) : <p className="empty-state">当前还没有学习轨迹。</p>)}</div></section><section className="support-panel"><div className="panel-heading"><h2>复习安排</h2><span>{reviews.length} 项</span></div>{reviews.length ? reviews.map((review) => <div className="overview-row" key={review.id}><span><strong>{review.reason}</strong><small>截止：{new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span></div>) : <p className="empty-state">当前没有待复习任务。</p>}</section></div>;
}

export function StudentMePage() {
  const [summary, setSummary] = useState<MemorySummary | null>(null);
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [notice, setNotice] = useState("正在读取个人学习信息…");
  const [deleting, setDeleting] = useState(false);
  const [challenge, setChallenge] = useState<{
    request_id: string;
    status_credential: string;
  } | null>(null);
  const [recoverySaved, setRecoverySaved] = useState(false);
  const [receipt, setReceipt] = useState<{
    request_id: string;
    status: string;
    note: string;
    attempt_count: number;
    retryable: boolean;
    last_error_code: string | null;
    status_credential_expires_at: string;
  } | null>(null);

  const load = () =>
    Promise.all([
      api<MemorySummary>("/me/memory"),
      api<MemoryItem[]>("/me/memory/items?limit=20"),
    ])
      .then(([nextSummary, nextItems]) => {
        setSummary(nextSummary);
        setItems(nextItems);
        setNotice("");
      })
      .catch((reason) => setNotice(message(reason)));

  useEffect(() => { void load(); }, []);

  async function submitDeletion() {
    if (!challenge || !recoverySaved) return;
    setDeleting(true);
    setNotice("");
    try {
      const nextReceipt = await api<typeof receipt>("/me/privacy/delete-request", {
        method: "POST",
        body: JSON.stringify(challenge),
      });
      if (!nextReceipt) throw new Error("删除请求未返回回执");
      setReceipt(nextReceipt);
      setSummary(null);
      setItems([]);
      setNotice(nextReceipt.note);
    } catch (reason) {
      setNotice(
        `请求结果暂未确认：账号可能已停用。请保留上方回执编号和查询凭证，` +
        `然后打开状态核验页查询或重试。${message(reason)}`,
      );
    } finally {
      setDeleting(false);
    }
  }

  const summaryEntries = summary ? Object.entries(summary.summary ?? {}) : [];
  const memoryKindLabels: Record<string, string> = { strength: "稳定表现", weakness: "待复核薄弱点", preference: "学习偏好", goal: "学习目标", fact: "学习事实" };
  const provenanceLabels: Record<string, string> = { observed: "直接观察", inferred: "根据证据推断", explicit: "本人明确提供", teacher_confirmed: "教师确认" };

  return (
    <div className="student-support-page">
      <div className="page-heading">
        <div><h1>我的</h1><p>查看学习摘要，并管理隐私删除请求。</p></div>
      </div>
      {notice && <p className="status-banner" role="status">{notice}</p>}
      <StudentPreferencesPanel />
      <StudentNotificationsPanel />
      <div className="practice-grid">
        <section className="support-panel">
          <div className="panel-heading"><h2>学习摘要</h2></div>
          {summaryEntries.length ? summaryEntries.map(([label, value]) => (
            <div className="overview-row" key={label}>
              <span><strong>{label.split(":").slice(1).join(":") || label}</strong><small>{label.startsWith("L1:") ? "短期学习记忆" : label.startsWith("L2:") ? "课程学习记忆" : label.startsWith("L3:") ? "长期学习记忆" : "学习记忆"} · {String(value)} 条</small></span>
            </div>
          )) : <p className="empty-state">暂无当前有效的学习记忆。</p>}
          {summary && summary.stale_hidden > 0 && <p className="empty-state">另有 {summary.stale_hidden} 条过期记忆已隐藏，不参与当前学习建议。</p>}
        </section>
        <section className="support-panel">
          <div className="panel-heading"><h2>隐私删除</h2></div>
          <p>请求提交前会先生成回执编号和随机查询凭证。请先保存两项信息；账号停用后，只有这两项可以核验或重试删除工作单。</p>
          {!challenge && !receipt && (
            <button
              className="secondary-button"
              onClick={() => {
                setChallenge(createDeletionRecoveryMaterial());
                setRecoverySaved(false);
              }}
            >准备删除请求</button>
          )}
          {challenge && !receipt && (
            <div className="data-panel" aria-live="polite">
              <h3>先保存恢复信息，再提交</h3>
              <p>回执编号</p><code>{challenge.request_id}</code>
              <p>查询凭证（仅你持有；请勿公开分享）</p><code>{challenge.status_credential}</code>
              <p>删除请求提交后会立即停用账号。若网络中断，你仍可用以上信息查询状态或安全重试；系统只保存凭证哈希。</p>
              <label>
                <input
                  type="checkbox"
                  checked={recoverySaved}
                  onChange={(event) => setRecoverySaved(event.target.checked)}
                />
                我已把回执编号和查询凭证保存到安全位置
              </label>
              <div className="attempt-actions">
                <button
                  className="secondary-button"
                  disabled={deleting}
                  onClick={() => { setChallenge(null); setRecoverySaved(false); }}
                >取消</button>
                <button
                  className="primary-button"
                  disabled={deleting || !recoverySaved}
                  onClick={() => void submitDeletion()}
                >{deleting ? "正在受理…" : "确认并提交删除请求"}</button>
              </div>
            </div>
          )}
          {receipt && (
            <div className="data-panel" aria-live="polite">
              <h3>删除工作单</h3>
              <p>状态：{receipt.status}</p>
              <p>回执编号：<code>{receipt.request_id}</code></p>
              <p>查询凭证：<code>{challenge?.status_credential}</code></p>
              <p>{receipt.note}</p>
              {receipt.retryable && <p>当前工作单可在状态核验页安全重试。</p>}
              <p><Link href="/privacy/deletion-status">打开隐私删除状态核验页</Link></p>
            </div>
          )}
        </section>
      </div>
      <section className="support-panel memory-list">
        <div className="panel-heading"><h2>学习记忆</h2><span>{items.length} 条</span></div>
        {items.length ? items.map((item) => (
          <article className="overview-row" key={item.id}>
            <span>
              <strong>{memoryKindLabels[item.kind] ?? item.kind}</strong>
              <small>{item.content}</small>
              <small>{item.layer} · {provenanceLabels[item.provenance_level] ?? item.provenance_level} · 依据 {item.evidence_refs.length} 条 · 置信度 {Math.round(item.confidence * 100)}%</small>
              <small>{item.needs_review ? "需要复核" : "当前有效"} · 更新于 {new Date(item.updated_at).toLocaleDateString("zh-CN")}{item.review_after ? ` · 复核日期 ${new Date(item.review_after).toLocaleDateString("zh-CN")}` : ""}</small>
            </span>
          </article>
        )) : <p className="empty-state">暂无可展示的学习记录。</p>}
      </section>
    </div>
  );
}
