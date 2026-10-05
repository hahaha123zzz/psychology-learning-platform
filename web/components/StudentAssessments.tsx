"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";

type Course = { id: string; title: string }; type Answer = string | string[] | boolean; type Assessment = { id: string; title: string; availability: string; ai_policy: string; opens_at?: string | null; closes_at?: string | null; current_attempt_id?: string | null; latest_completed_attempt_id?: string | null }; type Item = { question_version_id: string; order_no: number; points: number; type: string; stem: string; options?: { key: string; text: string }[] }; type Detail = { id: string; title: string; closes_at?: string | null; items: Item[] }; type Result = { score: number | null; grading_status: string; items: { question_version_id: string; points_earned: number | null; explanation?: string }[] };
type StartedAttempt = { attempt_id: string; answers: { question_version_id: string; response: { selected_keys?: string[] | boolean; text?: string } | null; answer_version: number; flagged: boolean }[] };
const fail = (reason: unknown) => reason instanceof ApiError ? reason.message : "请求失败，请稍后重试。";
const hasAnswer = (answer: Answer | undefined): boolean => Array.isArray(answer) ? answer.length > 0 : answer !== undefined && answer !== "";
export default function StudentAssessments() {
  const [courses, setCourses] = useState<Course[]>([]); const [courseId, setCourseId] = useState(""); const [list, setList] = useState<Assessment[]>([]); const [precheck, setPrecheck] = useState<Assessment | null>(null); const [detail, setDetail] = useState<Detail | null>(null); const [attemptId, setAttemptId] = useState(""); const [closedAttemptId, setClosedAttemptId] = useState(""); const [answers, setAnswers] = useState<Record<string, Answer>>({}); const [flagged, setFlagged] = useState<Record<string, boolean>>({}); const [saveState, setSaveState] = useState<Record<string, "editing" | "saving" | "saved" | "error">>({}); const [showReview, setShowReview] = useState(false); const [confirmSubmit, setConfirmSubmit] = useState(false); const [now, setNow] = useState(0); const [result, setResult] = useState<Result | null>(null); const [notice, setNotice] = useState(""); const [submitting, setSubmitting] = useState(false);
  const answerValues = useRef<Record<string, Answer>>({});
  const answerVersions = useRef<Record<string, number>>({});
  const saveQueues = useRef<Record<string, Promise<void>>>({});
  const pendingSaves = useRef<Record<string, number>>({});
  const saveFailureNotices = useRef<Record<string, string>>({});
  const essayTimers = useRef<Record<string, number>>({});
  const didAutoResume = useRef(false);
  const autoSubmitAttempt = useRef("");
  const submitInFlight = useRef(false);
  const begin = useCallback(async (item: Assessment) => { try { const [assessment, attempt] = await Promise.all([api<Detail>(`/assessments/${item.id}`), api<StartedAttempt>(`/assessments/${item.id}/attempts`, { method: "POST" })]); const restoredAnswers: Record<string, Answer> = {}; const restoredVersions: Record<string, number> = {}; const restoredFlags: Record<string, boolean> = {}; for (const saved of attempt.answers) { const selected = saved.response?.selected_keys; const questionType = assessment.items.find(question => question.question_version_id === saved.question_version_id)?.type; const value = typeof selected === "boolean" ? selected : Array.isArray(selected) ? questionType === "single" ? selected[0] : selected : saved.response?.text; if (value !== undefined) restoredAnswers[saved.question_version_id] = value; restoredVersions[saved.question_version_id] = saved.answer_version; restoredFlags[saved.question_version_id] = saved.flagged; } Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); essayTimers.current = {}; answerValues.current = restoredAnswers; answerVersions.current = restoredVersions; saveQueues.current = {}; pendingSaves.current = {}; saveFailureNotices.current = {}; autoSubmitAttempt.current = ""; submitInFlight.current = false; setSubmitting(false); setDetail(assessment); setAttemptId(attempt.attempt_id); setAnswers(restoredAnswers); setFlagged(restoredFlags); setSaveState({}); setShowReview(false); setConfirmSubmit(false); setPrecheck(null); setResult(null); } catch (reason) { setNotice(fail(reason)); } }, []);
  const finalizeClosedAttempt = useCallback(async (id: string) => {
    if (!id || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    setClosedAttemptId(id);
    setAttemptId(id);
    setNotice("检测到已截止但尚未封存的作答，正在提交服务端已保存答案…");
    try {
      await api(`/attempts/${id}/submit`, { method: "POST" });
      const recoveredResult = await api<Result>(`/attempts/${id}/result`);
      setResult(recoveredResult);
      setClosedAttemptId("");
      setNotice("");
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "ASSESSMENT_RESULT_NOT_RELEASED") {
        setClosedAttemptId("");
        setDetail(null);
        setAttemptId("");
        setNotice("答案已提交；结果将在测评策略规定的时间开放。此期间不会显示分数或解析。");
        if (courseId) setList(await api<Assessment[]>(`/courses/${courseId}/assessments`));
      } else {
        setNotice(`${fail(reason)} 可重试恢复服务端已保存的结果。`);
      }
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  }, [courseId]);
  const load = useCallback(async (id = courseId) => { if (!id) return; try { const assessments = await api<Assessment[]>(`/courses/${id}/assessments`); setList(assessments); if (!didAutoResume.current) { didAutoResume.current = true; const active = assessments.find(item => item.current_attempt_id && item.availability === "open"); if (active) await begin(active); else { const closedAttempt = assessments.find(item => item.current_attempt_id && item.availability === "closed"); if (closedAttempt?.current_attempt_id) await finalizeClosedAttempt(closedAttempt.current_attempt_id); } } } catch (reason) { setNotice(fail(reason)); } }, [begin, courseId, finalizeClosedAttempt]);
  useEffect(() => { api<Course[]>("/courses").then(data => { setCourses(data); const requestedCourseId = new URLSearchParams(window.location.search).get("course_id"); setCourseId(requestedCourseId && data.some(course => course.id === requestedCourseId) ? requestedCourseId : data[0]?.id ?? ""); }).catch(reason => setNotice(fail(reason))); }, []);
  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => { if (!detail?.closes_at) return; const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, [detail?.closes_at]);
  useEffect(() => () => { Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer)); }, []);
  async function saveResponse(questionId: string, response: Record<string, unknown>) { if (!attemptId) return; pendingSaves.current[questionId] = (pendingSaves.current[questionId] ?? 0) + 1; setSaveState(items => ({ ...items, [questionId]: "saving" })); const prior = saveQueues.current[questionId] ?? Promise.resolve(); const queued = prior.catch(() => undefined).then(async () => { let failed = false; try { const result = await api<{ answer_version: number }>(`/attempts/${attemptId}/answers/${questionId}`, { method: "PUT", body: JSON.stringify({ answer_version: answerVersions.current[questionId] ?? 1, response, client_saved_at: new Date().toISOString() }) }); answerVersions.current[questionId] = result.answer_version; const previousNotices = Object.values(saveFailureNotices.current); delete saveFailureNotices.current[questionId]; if (Object.keys(saveFailureNotices.current).length === 0) setNotice(current => previousNotices.includes(current) ? "" : current); } catch (reason) { failed = true; const message = fail(reason); saveFailureNotices.current[questionId] = message; setNotice(message); } finally { pendingSaves.current[questionId] = Math.max(0, (pendingSaves.current[questionId] ?? 1) - 1); if (pendingSaves.current[questionId] === 0) setSaveState(items => ({ ...items, [questionId]: failed ? "error" : "saved" })); } }); saveQueues.current[questionId] = queued; await queued; }
  function setAnswer(questionId: string, value: Answer) { answerValues.current[questionId] = value; setAnswers(items => ({ ...items, [questionId]: value })); }
  function save(questionId: string, key: string) { setAnswer(questionId, key); void saveResponse(questionId, { selected_keys: [key] }); }
  function saveMultiple(questionId: string, key: string, checked: boolean) { const current = answerValues.current[questionId]; const selected = Array.isArray(current) ? current : []; const next = checked ? [...selected.filter(value => value !== key), key] : selected.filter(value => value !== key); setAnswer(questionId, next); void saveResponse(questionId, { selected_keys: next }); }
  function saveTrueFalse(questionId: string, value: boolean) { setAnswer(questionId, value); void saveResponse(questionId, { selected_keys: value }); }
  function queueEssaySave(questionId: string, value: string) { setAnswer(questionId, value); setSaveState(items => ({ ...items, [questionId]: "editing" })); const old = essayTimers.current[questionId]; if (old !== undefined) window.clearTimeout(old); essayTimers.current[questionId] = window.setTimeout(() => { delete essayTimers.current[questionId]; void saveResponse(questionId, { text: value }); }, 600); }
  function flushEssaySave(questionId: string) { const timer = essayTimers.current[questionId]; if (timer !== undefined) { window.clearTimeout(timer); delete essayTimers.current[questionId]; void saveResponse(questionId, { text: answerValues.current[questionId] ?? "" }); } }
  async function toggleFlag(questionId: string) { if (!attemptId || !hasAnswer(answerValues.current[questionId])) return; const pending = saveQueues.current[questionId]; if (pending) await pending; const nextFlag = !flagged[questionId]; try { const response = await api<{ answer_version: number; flagged: boolean }>(`/attempts/${attemptId}/answers/${questionId}/flag`, { method: "PUT", body: JSON.stringify({ answer_version: answerVersions.current[questionId] ?? 1, flagged: nextFlag }) }); setFlagged(items => ({ ...items, [questionId]: response.flagged })); answerVersions.current[questionId] = response.answer_version; } catch (reason) { setNotice(fail(reason)); } }
  const submit = useCallback(async (automatic = false) => {
    if (!attemptId || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    try {
      if (automatic) {
        const unsentEssays = Object.keys(essayTimers.current);
        Object.values(essayTimers.current).forEach((timer) => window.clearTimeout(timer));
        essayTimers.current = {};
        if (unsentEssays.length > 0) {
          setSaveState((current) => ({ ...current, ...Object.fromEntries(unsentEssays.map((id) => [id, "error" as const])) }));
          setNotice("截止时有论述答案仍未完成自动保存；结果将只包含服务端已保存的答案。");
        }
        await Promise.all(Object.values(saveQueues.current).map((queued) => queued.catch(() => undefined)));
      }
      await api(`/attempts/${attemptId}/submit`, { method: "POST" });
      setConfirmSubmit(false);
      try {
        setResult(await api<Result>(`/attempts/${attemptId}/result`));
        setNotice("");
      } catch (reason) {
        if (reason instanceof ApiError && reason.code === "ASSESSMENT_RESULT_NOT_RELEASED") {
          setDetail(null);
          setAttemptId("");
          setNotice("答案已提交；结果将在测评策略规定的时间开放。此期间不会显示分数或解析。");
          await load();
        } else {
          throw reason;
        }
      }
    } catch (reason) {
      setNotice(fail(reason));
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  }, [attemptId, load]);
  async function viewResult(id: string) { try { setResult(await api<Result>(`/attempts/${id}/result`)); setNotice(""); } catch (reason) { setNotice(reason instanceof ApiError && reason.code === "ASSESSMENT_RESULT_NOT_RELEASED" ? "结果尚未按测评策略开放；开放后可从此处查看。" : fail(reason)); } }
  const remainingSeconds = detail?.closes_at && now > 0 ? Math.max(0, Math.ceil((Date.parse(detail.closes_at) - now) / 1000)) : null;
  useEffect(() => {
    if (remainingSeconds !== 0 || !attemptId || result || autoSubmitAttempt.current === attemptId) return;
    autoSubmitAttempt.current = attemptId;
    void submit(true);
  }, [attemptId, remainingSeconds, result, submit]);
  const unansweredCount = detail?.items.filter(item => !hasAnswer(answers[item.question_version_id])).length ?? 0;
  const flaggedCount = Object.values(flagged).filter(Boolean).length;
  const savePending = Object.values(saveState).some(state => state === "editing" || state === "saving" || state === "error");
  const jumpToQuestion = (questionId: string) => document.getElementById(`question-${questionId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  return <main className="functional-app">
    <header className="app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><Link href="/student">教材学习</Link><strong>测验</strong></header>
    <div className="functional-layout"><aside className="functional-nav"><strong>课程</strong>{courses.map(course => <button className={course.id === courseId ? "data-nav active" : "data-nav"} key={course.id} onClick={() => setCourseId(course.id)}>{course.title}</button>)}</aside>
      <section className="functional-main"><div className="section-title"><div><p className="eyebrow">服务端时间与策略为准</p><h1>课程测验</h1><p>正式测评入口与练习分离；保存、截止和评分均由服务端裁决。</p></div></div>
        {notice && <p className="status-banner">{notice}</p>}
        {closedAttemptId && !result && !detail && <section className="support-panel"><p>该测验已截止，不能重新打开题目；这里只能封存并读取服务端已保存的作答结果。</p><button className="primary-button" disabled={submitting} onClick={() => void finalizeClosedAttempt(closedAttemptId)}>{submitting ? "正在恢复…" : "重试恢复已保存结果"}</button></section>}
        {!detail && !precheck && !result && <section className="data-panel"><h2>可参加测验</h2>{list.length ? list.map(item => <article className="question-card" key={item.id}><div><strong>{item.title}</strong><small>{item.availability} · {item.ai_policy}</small></div>{item.availability === "closed" && item.current_attempt_id ? <button className="primary-button" disabled={submitting} onClick={() => void finalizeClosedAttempt(item.current_attempt_id!)}>恢复已保存结果</button> : item.latest_completed_attempt_id ? <button className="primary-button" onClick={() => void viewResult(item.latest_completed_attempt_id!)}>查看结果状态</button> : <button className="primary-button" disabled={item.availability !== "open"} onClick={() => setPrecheck(item)}>{item.availability === "open" ? "开始或继续" : item.availability === "scheduled" ? "尚未开始" : "已结束"}</button>}</article>) : <p className="empty-state">当前没有开放测验。</p>}</section>}
        {!detail && precheck && <section className="data-panel"><p className="eyebrow">开考前确认</p><h2>{precheck.title}</h2><p>AI 策略：{precheck.ai_policy}。测验开始后，普通学习入口仍受服务端考试策略限制。</p>{precheck.opens_at && <p>开放时间：{new Date(precheck.opens_at).toLocaleString("zh-CN")}</p>}{precheck.closes_at && <p>截止时间：{new Date(precheck.closes_at).toLocaleString("zh-CN")}（以服务器时间为准）</p>}<div className="attempt-actions"><button className="secondary-button" onClick={() => setPrecheck(null)}>返回列表</button><button className="primary-button" onClick={() => void begin(precheck)}>确认并进入测验</button></div></section>}
        {detail && !result && <section className="data-panel"><div className="attempt-header"><div><p className="eyebrow">正式测评</p><h2>{detail.title}</h2><p>答案自动保存；刷新后可恢复。保存失败时请先处理提示，不要假定已提交。</p></div>{remainingSeconds !== null && <strong aria-live="polite">{remainingSeconds > 0 ? `剩余 ${Math.floor(remainingSeconds / 60)}分${remainingSeconds % 60}秒` : "已到截止时间"}</strong>}</div>
          <div className="attempt-actions"><span>已答 {detail.items.length - unansweredCount}/{detail.items.length} · 未答 {unansweredCount} · 标记 {flaggedCount}</span><button className="secondary-button" onClick={() => setShowReview(value => !value)}>{showReview ? "收起检查清单" : "检查未答/标记题目"}</button></div>
          <nav className="growth-tabs" aria-label="题目导航">{detail.items.map((item, index) => <button className="secondary-button" key={item.question_version_id} aria-label={`跳转第 ${index + 1} 题`} onClick={() => jumpToQuestion(item.question_version_id)}>{index + 1}{flagged[item.question_version_id] ? " ⚑" : hasAnswer(answers[item.question_version_id]) ? " ✓" : " ·"}</button>)}</nav>
          {showReview && <section className="support-panel"><h3>提交前检查</h3>{detail.items.filter(item => !hasAnswer(answers[item.question_version_id]) || flagged[item.question_version_id]).map(item => <button className="secondary-button" key={item.question_version_id} onClick={() => jumpToQuestion(item.question_version_id)}>{item.order_no} 题 · {hasAnswer(answers[item.question_version_id]) ? "已作答，待检查" : "尚未作答"}{flagged[item.question_version_id] ? " · 已标记" : ""}</button>)}{unansweredCount === 0 && flaggedCount === 0 && <p>没有未作答或标记题目。</p>}</section>}
          {detail.items.map(item => { const questionId = item.question_version_id; const answer = answers[questionId]; return <article className="assessment-item" id={`question-${questionId}`} key={questionId}><strong>{item.order_no}. {item.stem}</strong>{item.type === "essay" || item.type === "short_answer" ? <label className="assessment-text-answer">文字作答<textarea aria-label={`第 ${item.order_no} 题文字作答`} maxLength={12000} rows={5} value={typeof answer === "string" ? answer : ""} onChange={(event) => queueEssaySave(questionId, event.target.value)} onBlur={() => flushEssaySave(questionId)} /></label> : item.type === "true_false" ? <div role="group" aria-label={`第 ${item.order_no} 题判断题`}>{[[true, "是"], [false, "否"]].map(([value, label]) => <label className="check-row" key={String(value)}><input type="radio" name={questionId} checked={answer === value} onChange={() => saveTrueFalse(questionId, value as boolean)} />{label as string}</label>)}</div> : item.type === "multiple" ? item.options?.map(option => <label className="check-row" key={option.key}><input type="checkbox" checked={Array.isArray(answer) && answer.includes(option.key)} onChange={(event) => saveMultiple(questionId, option.key, event.target.checked)} />{option.key}. {option.text}</label>) : item.options?.map(option => <label className="check-row" key={option.key}><input type="radio" name={questionId} checked={answer === option.key} onChange={() => save(questionId, option.key)} />{option.key}. {option.text}</label>)}<label className="check-row"><input type="checkbox" checked={Boolean(flagged[questionId])} disabled={!hasAnswer(answer) || saveState[questionId] === "editing" || saveState[questionId] === "saving" || saveState[questionId] === "error"} onChange={() => void toggleFlag(questionId)} />标记此题，稍后检查</label><small role="status">{saveState[questionId] === "editing" ? "编辑中，尚未保存" : saveState[questionId] === "saving" ? "正在保存…" : saveState[questionId] === "error" ? "保存失败" : hasAnswer(answer) ? "已保存" : "尚未作答"}</small></article>; })}
          {remainingSeconds === 0 ? <section className="support-panel"><p role="status">{submitting ? "时间已到，正在提交服务端已保存的答案…" : "时间已到，答案已锁定。若自动提交未成功，可重试提交已保存答案。"}</p>{!submitting && <button className="primary-button" onClick={() => void submit(true)}>重试提交已保存答案</button>}</section> : !confirmSubmit ? <button className="primary-button" disabled={savePending || submitting} onClick={() => setConfirmSubmit(true)}>检查并提交</button> : <section className="support-panel"><h3>确认提交</h3><p>还有 {unansweredCount} 道未作答，{flaggedCount} 道已标记。提交后不能再修改答案或标记。</p>{savePending && <p role="alert">存在保存中或保存失败的答案，请确认网络并修复后再提交。</p>}<div className="attempt-actions"><button className="secondary-button" disabled={submitting} onClick={() => setConfirmSubmit(false)}>继续检查</button><button className="primary-button" disabled={savePending || submitting} onClick={() => void submit()}>确认提交测验</button></div></section>}
        </section>}
        {result && <section className="data-panel"><h2>测验结果</h2><p className="result-score">得分：{result.score ?? "待教师评分"}</p><p>评分状态：{result.grading_status}</p>{result.items.map(item => <div className="mini-row" key={item.question_version_id}><span><strong>{item.points_earned ?? "—"} 分</strong><small>{item.explanation ?? "暂无可显示解析"}</small></span></div>)}<button className="secondary-button" onClick={() => { setDetail(null); setResult(null); void load(); }}>返回测验列表</button></section>}
      </section>
    </div>
  </main>;
}
