"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";
import { createDeletionRecoveryMaterial } from "../lib/privacy-deletion";
import { listMyLearningEvents } from "../lib/learning-events";
import { isReviewEvidenceQualified, waitForReviewQualification } from "../lib/review-evidence";
import StudentMiniLabPanel from "./StudentMiniLabPanel";
import StudentPreferencesPanel from "./StudentPreferencesPanel";
import StudentNotificationsPanel from "./StudentNotificationsPanel";

type Assessment = { id: string; title: string; purpose: "practice" | "formal"; availability: string; ai_policy: string; current_attempt_id?: string | null };
type Question = { question_version_id: string; order_no: number; points: number; type: string; stem: string; options?: { key: string; text: string }[] };
type AssessmentDetail = { id: string; title: string; items: Question[] };
type StartedAttempt = { attempt_id: string; answers: { question_version_id: string; response: { selected_keys?: string[] | boolean; text?: string } | null; answer_version: number; flagged: boolean }[] };
type Result = { score: number | null; grading_status: string; items: { question_version_id: string; points_earned: number | null; explanation?: string }[] };
type ReviewQuestion = { type: string; stem: string; options?: { key: string; text: string }[] };
type ReviewAnswer = string | string[] | boolean;
type Review = { id: string; course_id: string; reason: string; due_at: string; version?: number; question?: ReviewQuestion; qualification_status?: string };
type GrowthLastEvidence = { source_type?: string | null; created_at?: string | null; dimension?: string | null; independence_status?: string | null };
type PracticeAnswer = string | string[] | boolean | undefined;
function hasPracticeAnswer(answer: PracticeAnswer): boolean {
  if (typeof answer === "boolean") return true;
  if (Array.isArray(answer)) return answer.length > 0;
  return typeof answer === "string" && answer.trim().length > 0;
}
type GrowthKnowledge = { knowledge_point: string; state: string; evidence_count: number; state_reason: string; algorithm_version: string; next_step: string; updated_at: string; last_evidence?: GrowthLastEvidence | null };
type GrowthTabs = { knowledge: GrowthKnowledge[]; skills: { skill: string; status: string; evidence_count: number; next_step: string }[]; misconceptions: { knowledge_point: string; status: string; explanation: string; confidence: number; updated_at: string }[]; trajectory: { date: string; evidence_count: number; knowledge_points: string[] }[]; hint_support_summary?: { attempt_count: number; supported_attempt_count: number; independent_attempt_count: number; other_attempt_count: number } | null };
type MemoryItem = { id: string; layer: string; kind: string; content: string; confidence: number; course_id: string | null; provenance_level: string; evidence_refs: string[]; valid_from: string | null; expires_at: string | null; review_after: string | null; needs_review: boolean; conflict_status: string; updated_at: string };
type MemorySummary = { summary: Record<string, number>; stale_hidden: number };
function message(reason: unknown): string { return reason instanceof ApiError ? reason.message : "请求未完成，请检查本地服务后重试。"; }
const unavailableGrowthEvidence = "不可用或已过期（原因未提供）";
function GrowthEvidenceMetadata({ evidence }: { evidence: GrowthLastEvidence | null | undefined }) {
  if (!evidence) return <small className="growth-evidence-unavailable">最近依据：{unavailableGrowthEvidence}</small>;
  const source = evidence.source_type?.trim() || unavailableGrowthEvidence;
  const dimension = evidence.dimension?.trim() || unavailableGrowthEvidence;
  const independence = evidence.independence_status?.trim() || unavailableGrowthEvidence;
  const timestamp = evidence.created_at ? Date.parse(evidence.created_at) : Number.NaN;
  const time = Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(timestamp)
    : unavailableGrowthEvidence;
  return <div className="growth-evidence-metadata" aria-label="最近学习依据元数据"><small>来源：{source}</small><small>时间：{time}</small><small>维度：{dimension}</small><small>独立性：{independence}</small></div>;
}
type GrowthHintSupportValue = NonNullable<GrowthTabs["hint_support_summary"]>;
function isGrowthHintSupportSummary(value: unknown): value is GrowthHintSupportValue {
  if (!value || typeof value !== "object") return false;
  const summary = value as Record<string, unknown>;
  return ["attempt_count", "supported_attempt_count", "independent_attempt_count", "other_attempt_count"].every((key) => {
    const count = summary[key];
    return typeof count === "number" && Number.isFinite(count) && Number.isInteger(count) && count >= 0;
  });
}
function GrowthHintSupportCard({ summary }: { summary: GrowthTabs["hint_support_summary"] }) {
  const heading = <div className="panel-heading"><h2 id="growth-hint-support-title">学习提示记录</h2><span>原始次数</span></div>;
  if (summary == null) return <section className="support-panel growth-panel growth-hint-support" aria-labelledby="growth-hint-support-title">{heading}<p className="empty-state" role="status">暂无足够记录。</p></section>;
  if (!isGrowthHintSupportSummary(summary)) return <section className="support-panel growth-panel growth-hint-support" aria-labelledby="growth-hint-support-title">{heading}<p className="status-banner" role="status">次数统计不可用。</p></section>;
  return <section className="support-panel growth-panel growth-hint-support" aria-labelledby="growth-hint-support-title">{heading}<ul><li>尝试总数：{summary.attempt_count}</li><li>有支持尝试：{summary.supported_attempt_count}</li><li>独立尝试：{summary.independent_attempt_count}</li><li>其他尝试：{summary.other_attempt_count}</li></ul>{summary.attempt_count === 0 && <p className="empty-state" role="status">暂无足够记录。</p>}</section>;
}
function reviewIsDue(review: Review) {
  const dueAt = Date.parse(review.due_at);
  return Number.isFinite(dueAt) && dueAt <= Date.now();
}

function reviewQuestionSupportsVerification(review: Review) {
  if (review.version === undefined || !review.question) return false;
  if (review.question.type === "true_false") return true;
  return (review.question.type === "single" || review.question.type === "multiple") &&
    Boolean(review.question.options?.length);
}

function reviewVerificationResponse(review: Review, answer: ReviewAnswer | undefined) {
  const question = review.question;
  if (review.version === undefined || !question) return null;
  if (question.type === "true_false") {
    return typeof answer === "boolean" ? { selected_keys: answer } : null;
  }
  const optionKeys = new Set((question.options ?? []).map((option) => option.key));
  if (question.type === "single") {
    return typeof answer === "string" && optionKeys.has(answer) ? { selected_keys: [answer] } : null;
  }
  if (question.type === "multiple") {
    return Array.isArray(answer) && answer.length > 0 && answer.every((key) => optionKeys.has(key))
      ? { selected_keys: [...new Set(answer)] }
      : null;
  }
  return null;
}

function ReviewAnswerControl({ review, answer, onChange }: {
  review: Review;
  answer: ReviewAnswer | undefined;
  onChange: (answer: ReviewAnswer) => void;
}) {
  const question = review.question;
  if (!question) return <p className="review-unsupported" role="status">此复习题型不支持答案验证；只能关闭任务，不会提交答案或形成学习证据。</p>;
  if (question.type === "single" && question.options?.length) {
    return <fieldset className="review-answer-control"><legend>单项选择</legend><label>选择复习答案<select aria-label="选择复习答案" value={typeof answer === "string" ? answer : ""} onChange={(event) => onChange(event.target.value)}><option value="">选择答案</option>{question.options.map((option) => <option key={option.key} value={option.key}>{option.key}. {option.text}</option>)}</select></label></fieldset>;
  }
  if (question.type === "multiple" && question.options?.length) {
    const selected = Array.isArray(answer) ? answer : [];
    return <fieldset className="review-answer-control"><legend>多项选择</legend>{question.options.map((option) => <label key={option.key}><input aria-label={`${option.key}. ${option.text}`} type="checkbox" checked={selected.includes(option.key)} onChange={(event) => onChange(event.target.checked ? [...new Set([...selected, option.key])] : selected.filter((key) => key !== option.key))} />{option.key}. {option.text}</label>)}</fieldset>;
  }
  if (question.type === "true_false") {
    return <fieldset className="review-answer-control"><legend>判断题</legend>{[{ value: true, label: "是" }, { value: false, label: "否" }].map((option) => <label key={String(option.value)}><input type="radio" name={`review-${review.id}`} checked={answer === option.value} onChange={() => onChange(option.value)} />{option.label}</label>)}</fieldset>;
  }
  return <p className="review-unsupported" role="status">此复习题型不支持答案验证；只能关闭任务，不会提交答案或形成学习证据。</p>;
}

export function StudentPracticePage() {
  const { courseId } = useParams<{ courseId: string }>();
  const essayTimers = useRef<Record<string, number>>({});
  const answerVersions = useRef<Record<string, number>>({});
  const saveRequests = useRef<Record<string, Promise<boolean>>>({});
  const saveErrors = useRef<Record<string, boolean>>({});
  const [assessments, setAssessments] = useState<Assessment[]>([]); const [reviews, setReviews] = useState<Review[]>([]); const [reviewAnswers, setReviewAnswers] = useState<Record<string, ReviewAnswer>>({}); const [detail, setDetail] = useState<AssessmentDetail | null>(null); const [attemptId, setAttemptId] = useState(""); const [answers, setAnswers] = useState<Record<string, string | string[] | boolean>>({}); const [flagged, setFlagged] = useState<Record<string, boolean>>({}); const [saveState, setSaveState] = useState<Record<string, "editing" | "saving" | "saved" | "error">>({}); const [result, setResult] = useState<Result | null>(null); const [notice, setNotice] = useState("正在读取练习…");
  const open = useCallback(async (assessment: Assessment) => { try { const [nextDetail, attempt] = await Promise.all([api<AssessmentDetail>(`/assessments/${assessment.id}`), api<StartedAttempt>(`/assessments/${assessment.id}/attempts`, { method: "POST" })]); const restoredAnswers: Record<string, string | string[] | boolean> = {}; const restoredVersions: Record<string, number> = {}; const restoredFlags: Record<string, boolean> = {}; for (const saved of attempt.answers) { const selected = saved.response?.selected_keys; const answer = saved.response?.text; const questionType = nextDetail.items.find((item) => item.question_version_id === saved.question_version_id)?.type; if (Array.isArray(selected)) restoredAnswers[saved.question_version_id] = questionType === "single" ? selected[0] ?? "" : selected; else if (typeof selected === "boolean") restoredAnswers[saved.question_version_id] = selected; else if (typeof answer === "string") restoredAnswers[saved.question_version_id] = answer; restoredVersions[saved.question_version_id] = saved.answer_version; restoredFlags[saved.question_version_id] = saved.flagged; } Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); essayTimers.current = {}; answerVersions.current = restoredVersions; saveRequests.current = {}; saveErrors.current = {}; setDetail(nextDetail); setAttemptId(attempt.attempt_id); setAnswers(restoredAnswers); setFlagged(restoredFlags); setSaveState({}); setResult(null); setNotice(""); } catch (reason) { setNotice(message(reason)); } }, []);
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
  }, [courseId]);
  // 此 effect 仅发起路由课程对应的外部 API 加载，状态在异步请求完成后更新。
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => { Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); }, []);
  async function completeReview(task: Review) { try { await api(`/review-tasks/${task.id}/complete`, { method: "POST" }); setReviews((items) => items.filter((item) => item.id !== task.id)); setNotice("复习任务已关闭；此操作未提交答案，也未形成学习证据。"); } catch (reason) { setNotice(message(reason)); } }
  async function verifyReview(task: Review) {
    const selected = reviewAnswers[task.id];
    const response = reviewVerificationResponse(task, selected);
    if (!response || !reviewIsDue(task)) return;

    let result: { event_id: string; pending_qualification: boolean };
    try {
      result = await api<{ event_id: string; pending_qualification: boolean }>(
        `/review-tasks/${task.id}/verify`,
        {
          method: "POST",
          body: JSON.stringify({ version: task.version, response }),
        },
      );
    } catch (reason) {
      setNotice(message(reason));
      return;
    }

    setReviews((items) => items.filter((item) => item.id !== task.id));
    setReviewAnswers((items) => {
      const next = { ...items };
      delete next[task.id];
      return next;
    });
    setNotice(result.pending_qualification ? "复习答案已提交，学习记录正在等待资格判定…" : "复习答案已提交，正在核对学习记录结果…");

    let status: Awaited<ReturnType<typeof waitForReviewQualification>>;
    try {
      status = await waitForReviewQualification(result.event_id, courseId, () => listMyLearningEvents(courseId));
    } catch (reason) {
      setNotice(`复习答案已提交，但暂时无法确认学习记录状态：${message(reason)}`);
      return;
    }

    if (isReviewEvidenceQualified(status)) {
      setNotice("复习记录已通过资格确认；进入成长页时会重新读取当前信息。");
    } else if (status === "invalidated") {
      setNotice("复习学习记录已失效；成长信息未更新。");
    } else if (status === "rejected") {
      setNotice("复习答案已提交，但未通过学习证据资格确认；成长信息未更新。");
    } else {
      setNotice("复习答案已提交，学习记录仍在处理中；确认完成前成长信息不会更新。");
    }
  }
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
  function saveBoolean(questionId: string, selected: boolean) { setAnswers((items) => ({ ...items, [questionId]: selected })); void saveResponse(questionId, { selected_keys: selected }); }
  function saveMultiple(questionId: string, selected: string, checked: boolean) { const current = answers[questionId]; const prior = Array.isArray(current) ? current : []; const next = checked ? [...new Set([...prior, selected])] : prior.filter((key) => key !== selected); setAnswers((items) => ({ ...items, [questionId]: next })); void saveResponse(questionId, { selected_keys: next }); }
  function queueEssaySave(questionId: string, value: string) { setAnswers((items) => ({ ...items, [questionId]: value })); setSaveState((items) => ({ ...items, [questionId]: "editing" })); const old = essayTimers.current[questionId]; if (old !== undefined) window.clearTimeout(old); essayTimers.current[questionId] = window.setTimeout(() => { delete essayTimers.current[questionId]; void saveResponse(questionId, { text: value }); }, 600); }
  function flushEssaySave(questionId: string) { const timer = essayTimers.current[questionId]; if (timer !== undefined) { window.clearTimeout(timer); delete essayTimers.current[questionId]; void saveResponse(questionId, { text: answers[questionId] ?? "" }); } }
  async function toggleFlag(questionId: string) { if (!attemptId || !hasPracticeAnswer(answers[questionId])) return; const nextFlag = !flagged[questionId]; try { const response = await api<{ answer_version: number; flagged: boolean }>(`/attempts/${attemptId}/answers/${questionId}/flag`, { method: "PUT", body: JSON.stringify({ answer_version: answerVersions.current[questionId] ?? 1, flagged: nextFlag }) }); answerVersions.current[questionId] = response.answer_version; setFlagged((items) => ({ ...items, [questionId]: response.flagged })); } catch (reason) { setNotice(message(reason)); } }
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
  return <div className="student-support-page"><div className="page-heading"><div><h1>练习与复习</h1><p>练习只显示 purpose=practice；正式测评在独立 Assessment 页面中进行。</p></div></div>{notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}{!detail ? <div className="practice-grid"><section className="support-panel"><div className="panel-heading"><h2>待复习</h2><span>{reviews.length} 项</span></div>{reviews.length ? reviews.map((review) => { const due = reviewIsDue(review); const canVerify = reviewQuestionSupportsVerification(review); const response = reviewVerificationResponse(review, reviewAnswers[review.id]); return <article className="review-row" data-review-task-id={review.id} key={review.id}><span><strong>{review.reason}</strong><small>{review.question?.stem ?? "复习任务"} · 可复习时间：{new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span><span className="review-actions">{canVerify ? <><ReviewAnswerControl review={review} answer={reviewAnswers[review.id]} onChange={(answer) => setReviewAnswers((items) => ({ ...items, [review.id]: answer }))} /><button className="secondary-button" aria-describedby={!due ? `review-due-${review.id}` : undefined} disabled={!response || !due} onClick={() => void verifyReview(review)}>验证并完成</button>{!due && <small id={`review-due-${review.id}`} role="status">尚未到可复习时间，届时可验证并完成。</small>}</> : <><p className="review-unsupported" role="status">此复习题型不支持答案验证；关闭任务不会提交答案或形成学习证据。</p><button className="secondary-button" onClick={() => void completeReview(review)}>关闭复习任务（不提交答案）</button></>}</span></article>; }) : <p className="empty-state">暂无待复习任务。</p>}</section><section className="support-panel"><div className="panel-heading"><h2>可参加的练习</h2><span>{assessments.length} 个</span></div><p>正式测评与练习分开；练习作答会保存进度并在提交后显示反馈。</p>{assessments.length ? assessments.map((assessment) => <article className="review-row" key={assessment.id}><span><strong>{assessment.title}</strong><small>{assessment.availability}</small></span><button className="primary-button" disabled={assessment.availability !== "open"} onClick={() => void open(assessment)}>{assessment.current_attempt_id ? "恢复练习" : assessment.availability === "open" ? "开始练习" : "暂不可参加"}</button></article>) : <p className="empty-state">当前课程没有可参加的练习。</p>}</section></div> : !result ? <section className="attempt-panel"><div className="attempt-header"><div><h2>{detail.title}</h2><p>作答将自动保存；提交后由服务端评分。</p></div><span>{Object.values(answers).filter(hasPracticeAnswer).length} / {detail.items.length} 已作答</span></div>{detail.items.map((item) => <article className="attempt-question" key={item.question_version_id}><strong>{item.order_no}. {item.stem}</strong>{item.type === "essay" || item.type === "short_answer" ? <label className="assessment-text-answer">文字作答<textarea aria-label={`第 ${item.order_no} 题文字作答`} maxLength={12000} rows={5} value={typeof answers[item.question_version_id] === "string" ? answers[item.question_version_id] as string : ""} onChange={(event) => queueEssaySave(item.question_version_id, event.target.value)} onBlur={() => flushEssaySave(item.question_version_id)} /></label> : item.type === "true_false" ? <fieldset><legend>请选择判断</legend>{[{ value: true, label: "是" }, { value: false, label: "否" }].map((option) => <label key={String(option.value)}><input type="radio" name={item.question_version_id} checked={answers[item.question_version_id] === option.value} onChange={() => saveBoolean(item.question_version_id, option.value)} />{option.label}</label>)}</fieldset> : item.type === "multiple" ? item.options?.map((option) => <label key={option.key}><input type="checkbox" checked={Array.isArray(answers[item.question_version_id]) && (answers[item.question_version_id] as string[]).includes(option.key)} onChange={(event) => saveMultiple(item.question_version_id, option.key, event.target.checked)} />{option.key}. {option.text}</label>) : item.options?.map((option) => <label key={option.key}><input type="radio" name={item.question_version_id} checked={answers[item.question_version_id] === option.key} onChange={() => void save(item.question_version_id, option.key)} />{option.key}. {option.text}</label>)}<label><input type="checkbox" checked={Boolean(flagged[item.question_version_id])} disabled={!hasPracticeAnswer(answers[item.question_version_id]) || savePending} onChange={() => void toggleFlag(item.question_version_id)} />标记此题，稍后检查</label><small role="status">{saveState[item.question_version_id] === "editing" ? "编辑中，尚未保存" : saveState[item.question_version_id] === "saving" ? "正在保存…" : saveState[item.question_version_id] === "error" ? "保存失败" : hasPracticeAnswer(answers[item.question_version_id]) ? "已保存" : "尚未作答"}</small></article>)}{saveFailed && <p role="alert">答案保存失败，请修改或重试后再提交。</p>}<div className="attempt-actions"><button className="secondary-button" onClick={() => setDetail(null)}>返回练习</button><button className="primary-button" disabled={savePending || saveFailed} onClick={() => void submit()}>提交练习</button></div></section> : <section className="attempt-panel result-panel"><Icon icon="solar:check-circle-bold" /><h2>练习完成</h2><strong>{result.score ?? "待教师评分"}</strong><p>评分状态：{result.grading_status}</p>{result.items.map((item) => <article className="result-row" key={item.question_version_id}><span>本题得分：{item.points_earned ?? "—"}</span><small>{item.explanation ?? "暂无可显示解析"}</small></article>)}<button className="secondary-button" onClick={() => { setDetail(null); setResult(null); void load(); }}>返回练习</button></section>}<StudentMiniLabPanel courseId={courseId} /></div>;
}

export function StudentGrowthPage() {
  const { courseId } = useParams<{ courseId: string }>(); const [knowledge, setKnowledge] = useState<GrowthKnowledge[]>([]); const [tabs, setTabs] = useState<GrowthTabs | null>(null); const [tab, setTab] = useState<"knowledge" | "skills" | "misconceptions" | "trajectory">("knowledge"); const [reviews, setReviews] = useState<Review[]>([]); const [focus, setFocus] = useState<{ knowledge_point: string; state: string; state_reason: string; next_step: string; last_evidence?: GrowthLastEvidence | null } | null>(null); const [dueCount, setDueCount] = useState(0); const [notice, setNotice] = useState("正在读取成长信息…");
  const tabKeys = ["knowledge", "skills", "misconceptions", "trajectory"] as const;
  const tabRefs = useRef<Partial<Record<(typeof tabKeys)[number], HTMLButtonElement>>>({});
  useEffect(() => { Promise.all([api<{ focus: { knowledge_point: string; state: string; state_reason: string; next_step: string; last_evidence?: GrowthLastEvidence | null } | null; attention: { due_review_count: number } }>(`/student/growth/overview?course_id=${courseId}`), api<GrowthKnowledge[]>(`/student/growth/knowledge?course_id=${courseId}`), api<GrowthTabs>(`/student/growth/tabs?course_id=${courseId}`), api<Review[]>("/review-tasks?due_only=false")]).then(([overview, nextKnowledge, nextTabs, nextReviews]) => { setFocus(overview.focus); setDueCount(overview.attention.due_review_count); setKnowledge(nextKnowledge); setTabs(nextTabs); setReviews(nextReviews.filter((review) => review.course_id === courseId)); setNotice(""); }).catch((reason) => setNotice(message(reason))); }, [courseId]);
  const tabLabels: Record<(typeof tabKeys)[number], string> = { knowledge: "知识", skills: "技能", misconceptions: "误区", trajectory: "轨迹" };
  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, current: (typeof tabKeys)[number]) {
    const currentIndex = tabKeys.indexOf(current);
    let nextIndex: number;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        nextIndex = (currentIndex + 1) % tabKeys.length;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        nextIndex = (currentIndex - 1 + tabKeys.length) % tabKeys.length;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = tabKeys.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const nextTab = tabKeys[nextIndex];
    setTab(nextTab);
    tabRefs.current[nextTab]?.focus();
  }
  const tabKnowledgeByPoint = new Map((tabs?.knowledge ?? []).map((item) => [item.knowledge_point, item]));
  return <div className="student-support-page"><div className="page-heading"><div><h1>成长</h1><p>根据你的学习与练习记录，查看当前掌握状态、依据和下一步行动。</p></div></div>{notice && <p className="status-banner" role="status">{notice}</p>}<section className="support-panel growth-panel"><div className="panel-heading"><h2>下一步</h2><span>{dueCount ? `${dueCount} 项到期复习` : "状态已更新"}</span></div>{focus ? <div className="growth-focus"><strong>{focus.knowledge_point}</strong><small>{focus.state} · {focus.next_step}</small><small>{focus.state_reason}</small><GrowthEvidenceMetadata evidence={focus.last_evidence} /></div> : <p className="empty-state">完成学习或测验后，这里会生成可解释的成长建议。</p>}</section><GrowthHintSupportCard summary={tabs?.hint_support_summary} /><section className="support-panel growth-panel"><div className="growth-tabs" role="tablist" aria-label="成长信息类别">{tabKeys.map((key) => <button type="button" className={key === tab ? "secondary-button active" : "secondary-button"} key={key} ref={(node) => { tabRefs.current[key] = node ?? undefined; }} tabIndex={key === tab ? 0 : -1} role="tab" aria-selected={key === tab} aria-controls="growth-tab-panel" id={`growth-tab-${key}`} onKeyDown={(event) => handleTabKeyDown(event, key)} onClick={() => setTab(key)}>{tabLabels[key]}</button>)}</div><div id="growth-tab-panel" role="tabpanel" aria-labelledby={`growth-tab-${tab}`}>{tab === "knowledge" && (knowledge.length ? knowledge.map((item) => <div className="growth-row" key={item.knowledge_point}><span><strong>{item.knowledge_point}</strong><small>{item.state} · 依据 {item.evidence_count} 条</small><small>{item.state_reason}</small><small>更新于 {new Date(item.updated_at).toLocaleDateString("zh-CN")} · 规则 {item.algorithm_version}</small><GrowthEvidenceMetadata evidence={tabKnowledgeByPoint.get(item.knowledge_point)?.last_evidence} /></span><em>{item.next_step}</em></div>) : <p className="empty-state">当前还没有足够的学习证据。</p>)}{tab === "skills" && <p className="empty-state">当前服务端只有知识点掌握记录，没有独立技能证据；此处不会把知识点状态当作技能结论。</p>}{tab === "misconceptions" && <p className="empty-state">当前没有经确认的误区定义；待复核的学习记忆不作为误区结论展示。</p>}{tab === "trajectory" && (tabs?.trajectory.length ? tabs.trajectory.map((item) => <div className="growth-row" key={item.date}><span><strong>{item.date}</strong><small>{item.knowledge_points.length} 个知识点</small></span><em>学习证据 {item.evidence_count} 条</em></div>) : <p className="empty-state">当前还没有学习轨迹。</p>)}</div></section><section className="support-panel"><div className="panel-heading"><h2>复习安排</h2><span>{reviews.length} 项</span></div>{reviews.length ? reviews.map((review) => <div className="overview-row" key={review.id}><span><strong>{review.reason}</strong><small>截止：{new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span></div>) : <p className="empty-state">当前没有待复习任务。</p>}</section></div>;
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
