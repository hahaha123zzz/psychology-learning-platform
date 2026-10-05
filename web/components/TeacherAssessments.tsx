"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";

type Course = { id: string; title: string };
type Question = { id: string; status: string; current_version?: { id: string; stem: string; type: string; evidence_ids: string[] } };
type RubricCriterion = { key: string; description: string; points: number; anchors: Record<string, string> };
type Rubric = { id: string; version_no: number; max_score: number; status: string; criteria: RubricCriterion[]; evidence_refs: string[]; created_by?: string; approved_by?: string };
type Assessment = { id: string; title: string; status: string; availability: string; ai_policy: string; purpose?: string; result_visibility_policy?: string; version: number; results_released_at?: string | null };
type RubricCriterionDraft = { key: string; description: string; points: string; zeroAnchor: string; fullAnchor: string };
type RubricDraft = { evidenceRef: string; criteria: RubricCriterionDraft[] };
type AssessmentPreview = { purpose: string; result_visibility_policy: string; total_points: number; blocking_issues: { code: string; message: string }[]; can_publish: boolean };
const failure = (reason: unknown) => reason instanceof ApiError ? reason.message : "请求失败，请稍后重试。";
export default function TeacherAssessments({ embedded = false, initialCourseId = "" }: { embedded?: boolean; initialCourseId?: string }) {
  const [courses, setCourses] = useState<Course[]>([]); const [courseId, setCourseId] = useState(initialCourseId); const [questions, setQuestions] = useState<Question[]>([]); const [rubricsByQuestion, setRubricsByQuestion] = useState<Record<string, Rubric[]>>({}); const [selectedRubrics, setSelectedRubrics] = useState<Record<string, string>>({}); const [rubricDrafts, setRubricDrafts] = useState<Record<string, RubricDraft>>({}); const [rubricApprovalReasons, setRubricApprovalReasons] = useState<Record<string, string>>({}); const [purposeReasons, setPurposeReasons] = useState<Record<string, string>>({}); const [purposeDecisions, setPurposeDecisions] = useState<Record<string, string>>({}); const [assessments, setAssessments] = useState<Assessment[]>([]); const [selected, setSelected] = useState<string[]>([]); const [notice, setNotice] = useState(""); const [preview, setPreview] = useState<AssessmentPreview | null>(null);
  const load = useCallback(async (id = courseId) => { if (!id) return; try { const [qs, as] = await Promise.all([api<Question[]>(`/courses/${id}/questions?status=published`), api<Assessment[]>(`/courses/${id}/assessments`)]); const rubricRows = await Promise.all(qs.filter(question => question.current_version?.id).map(async question => [question.id, await api<Rubric[]>(`/courses/${id}/rubrics?question_version_id=${question.current_version!.id}`)] as const)); setRubricsByQuestion(Object.fromEntries(rubricRows)); setQuestions(qs); setAssessments(as); setSelected([]); setSelectedRubrics({}); setPreview(null); } catch (reason) { setNotice(failure(reason)); } }, [courseId]);
  // 此 effect 仅请求外部课程列表；状态更新发生在异步响应回调中。
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { api<Course[]>("/courses").then(data => { setCourses(data); setCourseId(current => initialCourseId && data.some(course => course.id === initialCourseId) ? initialCourseId : current || data[0]?.id || ""); }).catch(reason => setNotice(failure(reason))); }, [initialCourseId]); useEffect(() => { void load(); }, [load]);
  async function create(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); if (!selected.length) return setNotice("请至少选择一道已发布题目。"); const localDate = (key: string) => { const value = String(form.get(key) ?? ""); return value ? new Date(value).toISOString() : null; }; const rubric_version_ids = Object.fromEntries(questions.filter(question => selected.includes(question.id) && selectedRubrics[question.id] && question.current_version?.id).map(question => [question.current_version!.id, selectedRubrics[question.id]])); const body = { title: String(form.get("title") ?? ""), question_ids: selected, rubric_version_ids, ai_policy: form.get("ai_policy"), purpose: form.get("purpose"), result_visibility_policy: form.get("result_visibility_policy"), opens_at: localDate("opens_at"), closes_at: localDate("closes_at"), points_per_question: 1 }; try { const gate = await api<AssessmentPreview>(`/courses/${courseId}/assessments/preview`, { method: "POST", body: JSON.stringify(body) }); setPreview(gate); if (!gate.can_publish) { setNotice(`预览发现 ${gate.blocking_issues.length} 项发布阻塞，请先处理题目用途或 Rubric。`); return; } if (!preview) { setNotice("服务端预览已通过。请检查用途、结果策略和总分，再次点击确认创建草稿。"); return; } await api(`/courses/${courseId}/assessments`, { method: "POST", body: JSON.stringify(body) }); setNotice("草稿已创建；发布仍需教师再次确认。"); formElement.reset(); await load(); } catch (reason) { setNotice(failure(reason)); } }
  async function publish(id: string) { try { await api(`/assessments/${id}/publish`, { method: "POST" }); setNotice("测验已发布，学生仅会在开放时间内看到题目。"); await load(); } catch (reason) { setNotice(failure(reason)); } }
  async function releaseResults(item: Assessment) { try { await api(`/assessments/${item.id}/release-results`, { method: "POST", body: JSON.stringify({ expected_version: item.version }) }); setNotice("测验结果已发布给学生。"); await load(); } catch (reason) { setNotice(failure(reason)); } }
  function draftFor(question: Question): RubricDraft {
    const versionId = question.current_version?.id ?? "";
    return rubricDrafts[versionId] ?? {
      evidenceRef: question.current_version?.evidence_ids?.[0] ?? "",
      criteria: [{ key: "criterion-1", description: "", points: "5", zeroAnchor: "未体现本项评分标准。", fullAnchor: "完整满足本项评分标准。" }],
    };
  }
  function updateRubricDraft(question: Question, update: (draft: RubricDraft) => RubricDraft) {
    const versionId = question.current_version?.id;
    if (!versionId) return;
    setRubricDrafts(current => ({ ...current, [versionId]: update(draftFor(question)) }));
  }
  async function refreshRubrics(question: Question) {
    const versionId = question.current_version?.id;
    if (!versionId) return;
    const rubrics = await api<Rubric[]>(`/courses/${courseId}/rubrics?question_version_id=${versionId}`);
    setRubricsByQuestion(current => ({ ...current, [question.id]: rubrics }));
  }
  async function createRubric(event: FormEvent<HTMLFormElement>, question: Question) {
    event.preventDefault();
    const versionId = question.current_version?.id;
    const draft = draftFor(question);
    if (!versionId || !draft.evidenceRef) return setNotice("该题目版本没有可引用证据，暂不能创建 Rubric。");
    const criteria = draft.criteria.map(item => ({
      key: item.key.trim(),
      description: item.description.trim(),
      points: Number(item.points),
      anchors: { "0": item.zeroAnchor.trim(), [item.points]: item.fullAnchor.trim() },
    }));
    if (criteria.some(item => !item.key || !item.description || !Number.isFinite(item.points) || item.points <= 0 || !item.anchors["0"] || !item.anchors[String(item.points)])) {
      return setNotice("请为每个评分项填写唯一标识、标准说明、正分值和 0/满分锚点。");
    }
    const body = { question_version_id: versionId, criteria, max_score: criteria.reduce((sum, item) => sum + item.points, 0), evidence_refs: [draft.evidenceRef] };
    try {
      await api(`/courses/${courseId}/rubrics`, { method: "POST", body: JSON.stringify(body) });
      await refreshRubrics(question);
      setRubricDrafts(current => { const next = { ...current }; delete next[versionId]; return next; });
      setNotice("Rubric 草稿版本已创建。需由另一位课程教师填写复核理由并批准后，才能用于正式测评。");
    } catch (reason) { setNotice(failure(reason)); }
  }
  async function approveRubric(question: Question, rubric: Rubric) {
    const reason = (rubricApprovalReasons[rubric.id] ?? "").trim();
    if (reason.length < 8) return setNotice("Rubric 审批理由至少需要 8 个字符。");
    try {
      await api(`/rubrics/${rubric.id}/approve`, { method: "POST", body: JSON.stringify({ reason }) });
      await refreshRubrics(question);
      setRubricApprovalReasons(current => ({ ...current, [rubric.id]: "" }));
      setNotice("Rubric 已批准；批准人不能与创建人相同。");
    } catch (reason) { setNotice(failure(reason)); }
  }
  async function decideFormalPurpose(question: Question, decision: "approved" | "revoked") {
    const versionId = question.current_version?.id;
    const reason = (purposeReasons[question.id] ?? "").trim();
    if (!versionId) return;
    if (reason.length < 8) return setNotice("正式用途审批理由至少需要 8 个字符。");
    try {
      await api(`/courses/${courseId}/question-versions/${versionId}/purpose/formal`, { method: "POST", body: JSON.stringify({ decision, reason }) });
      setPurposeDecisions(current => ({ ...current, [question.id]: decision }));
      setNotice(decision === "approved" ? "正式测评用途已批准；题目作者不能审批自己的题目。" : "正式测评用途已撤销，后续发布门禁将重新检查。");
    } catch (reason) { setNotice(failure(reason)); }
  }
  const content = <section className={embedded ? "" : "functional-main"}><div className="section-title"><div><p className="eyebrow">步骤 1 · 组卷　步骤 2 · 策略　步骤 3 · 预览发布</p><h1>测评发布向导</h1><p>先选择用途与结果可见策略，服务端预览通过后才会创建草稿；正式发布仍需再次确认。</p></div></div>{notice && <p className="status-banner">{notice}</p>}<div className="data-grid"><section className="data-panel"><h2>选择已发布题目</h2>{questions.length ? questions.map(question => <div className="check-row" key={question.id}><label><input type="checkbox" checked={selected.includes(question.id)} onChange={() => { setPreview(null); setSelected(items => items.includes(question.id) ? items.filter(id => id !== question.id) : [...items, question.id]); }} /><span>{question.current_version?.stem}</span></label><span>请在下方用途复核区填写理由后提交 formal 决议。</span>{selected.includes(question.id) && question.current_version?.type !== "single" && question.current_version?.type !== "multiple" && question.current_version?.type !== "true_false" && <label>评分 Rubric<select value={selectedRubrics[question.id] ?? ""} onChange={event => { setPreview(null); setSelectedRubrics(items => ({ ...items, [question.id]: event.target.value })); }}><option value="">选择已批准 Rubric</option>{(rubricsByQuestion[question.id] ?? []).filter(rubric => rubric.status === "approved").map(rubric => <option key={rubric.id} value={rubric.id}>v{rubric.version_no} · {rubric.max_score} 分</option>)}</select></label>}</div>) : <p className="empty-state">暂无已发布题目。请先在题库审核并发布。</p>}</section><section className="data-panel"><h2>测评与结果策略</h2><form className="stack-form" onChange={() => setPreview(null)} onSubmit={create}><label>测评名称<input name="title" placeholder="测验名称" required /></label><label>用途<select name="purpose" defaultValue="practice"><option value="practice">练习</option><option value="formal">正式测评</option></select></label><label>结果可见<select name="result_visibility_policy" defaultValue=""><option value="">按用途与题型推荐</option><option value="immediate_after_submission">提交后立即（仅练习）</option><option value="after_close">到截止时间后</option><option value="after_grading">评分完成后</option><option value="manual_release">教师手动发布</option></select></label><label>开放时间<input name="opens_at" type="datetime-local" /></label><label>截止时间<input name="closes_at" type="datetime-local" /></label><label>考试中 AI 策略<select name="ai_policy" defaultValue="disabled"><option value="disabled">禁用 AI</option><option value="direction_only">仅方向提示（当前 fail closed）</option><option value="full_after_submit">提交后完整解析</option></select></label><p className="empty-state">已选择 {selected.length} 题。formal 题目需由非作者教师批准；主观题还需选择已批准 Rubric。</p><button className="primary-button">{preview?.can_publish ? "确认创建草稿" : "预览门禁"}</button></form></section></div>{preview && <section className="data-panel"><h2>服务端预览 · {preview.purpose} · 总分 {preview.total_points}</h2><p>结果策略：{preview.result_visibility_policy}</p>{preview.blocking_issues.map((issue, index) => <p role="alert" key={`${issue.code}-${index}`}>{issue.code}：{issue.message}</p>)}{preview.can_publish && <p>门禁通过。创建的测验仍保持草稿，需单独确认发布。</p>}</section>}<section className="data-panel"><h2>测验列表</h2>{assessments.length ? assessments.map(item => <article className="question-card" key={item.id}><div><span className="status-chip">{item.status}</span><strong>{item.title}</strong><small>{item.purpose ?? "用途未设置"} · {item.result_visibility_policy ?? "结果策略缺失"} · {item.availability} · AI：{item.ai_policy}</small></div>{item.status !== "published" && <button className="primary-button" onClick={() => void publish(item.id)}>确认发布</button>}{item.status === "published" && item.result_visibility_policy === "manual_release" && !item.results_released_at && <button className="primary-button" onClick={() => void releaseResults(item)}>手动发布结果</button>}</article>) : <p className="empty-state">当前课程尚未创建测验。</p>}</section></section>;
  const rubricWorkspace = <section className="data-panel">
    <h2>题目用途与 Rubric 版本</h2>
    <p>Rubric 仅为教师人工评分提供版本化依据，不会自动评分或生成 AI 评分建议。formal 决议与 Rubric 审批均由服务端执行作者隔离检查；正式测评发布门禁仍以服务端预览结果为准。</p>
    {questions.map(question => {
      const version = question.current_version;
      if (!version) return null;
      const isSubjective = version.type === "short_answer" || version.type === "essay";
      const draft = draftFor(question);
      return <article className="question-card" key={question.id}>
        <div><strong>{version.stem}</strong><small>题目版本 {version.id} · {version.type}</small></div>
        <label>正式用途复核理由
          <textarea value={purposeReasons[question.id] ?? ""} minLength={8} maxLength={500} onChange={event => setPurposeReasons(current => ({ ...current, [question.id]: event.target.value }))} placeholder="说明审核依据（至少 8 个字符）" />
        </label>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void decideFormalPurpose(question, "approved")}>批准 formal 用途</button>
          <button type="button" className="secondary-button" onClick={() => void decideFormalPurpose(question, "revoked")}>撤销 formal 用途</button>
          {purposeDecisions[question.id] && <span role="status">本次操作：{purposeDecisions[question.id] === "approved" ? "已批准" : "已撤销"}</span>}
        </div>
        {!isSubjective ? <p className="empty-state">客观题不需要 Rubric。</p> : <>
          <h3>Rubric 版本</h3>
          {(rubricsByQuestion[question.id] ?? []).length ? (rubricsByQuestion[question.id] ?? []).map(rubric => <div className="question-card" key={rubric.id}>
            <strong>v{rubric.version_no} · {rubric.status} · {rubric.max_score} 分</strong>
            <ul>{rubric.criteria.map(criterion => <li key={criterion.key}>{criterion.description}（{criterion.points} 分；锚点 {Object.entries(criterion.anchors).map(([score, text]) => `${score}：${text}`).join("；")}）</li>)}</ul>
            <small>证据引用：{rubric.evidence_refs.join("、")}</small>
            {rubric.status === "draft" && <div className="stack-form">
              <label htmlFor={`rubric-reason-${rubric.id}`}>独立审批理由<textarea id={`rubric-reason-${rubric.id}`} value={rubricApprovalReasons[rubric.id] ?? ""} minLength={8} maxLength={500} onChange={event => setRubricApprovalReasons(current => ({ ...current, [rubric.id]: event.target.value }))} placeholder="说明评分标准的复核依据（至少 8 个字符）" /></label>
              <button type="button" className="secondary-button" onClick={() => void approveRubric(question, rubric)}>批准此版本</button>
            </div>}
          </div>) : <p className="empty-state">尚无 Rubric 版本。</p>}
          <details>
            <summary>创建新的 Rubric 草稿版本</summary>
            <form className="stack-form" onSubmit={event => void createRubric(event, question)}>
              <label>证据引用
                <select value={draft.evidenceRef} onChange={event => updateRubricDraft(question, current => ({ ...current, evidenceRef: event.target.value }))} required>
                  <option value="">选择此题目版本的证据</option>
                  {version.evidence_ids.map(evidenceId => <option key={evidenceId} value={evidenceId}>{evidenceId}</option>)}
                </select>
              </label>
              {draft.criteria.map((criterion, index) => <fieldset className="stack-form" key={`${version.id}-${index}`}>
                <legend>评分项 {index + 1}</legend>
                <label>评分项标识<input value={criterion.key} maxLength={80} onChange={event => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item) }))} required /></label>
                <label>评分标准<textarea value={criterion.description} maxLength={1000} onChange={event => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item) }))} required /></label>
                <label>该项满分<input type="number" min="0.01" step="any" value={criterion.points} onChange={event => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.map((item, itemIndex) => itemIndex === index ? { ...item, points: event.target.value } : item) }))} required /></label>
                <label>0 分锚点<textarea value={criterion.zeroAnchor} onChange={event => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.map((item, itemIndex) => itemIndex === index ? { ...item, zeroAnchor: event.target.value } : item) }))} required /></label>
                <label>满分锚点<textarea value={criterion.fullAnchor} onChange={event => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.map((item, itemIndex) => itemIndex === index ? { ...item, fullAnchor: event.target.value } : item) }))} required /></label>
                {draft.criteria.length > 1 && <button type="button" className="secondary-button" onClick={() => updateRubricDraft(question, current => ({ ...current, criteria: current.criteria.filter((_, itemIndex) => itemIndex !== index) }))}>删除此评分项</button>}
              </fieldset>)}
              <button type="button" className="secondary-button" onClick={() => updateRubricDraft(question, current => ({ ...current, criteria: [...current.criteria, { key: `criterion-${current.criteria.length + 1}`, description: "", points: "1", zeroAnchor: "未体现本项评分标准。", fullAnchor: "完整满足本项评分标准。" }] }))}>添加评分项</button>
              <button type="submit" className="primary-button" disabled={!version.evidence_ids.length}>创建 Rubric 草稿</button>
              {!version.evidence_ids.length && <p className="empty-state">题目版本没有证据引用，不能创建 Rubric。</p>}
            </form>
          </details>
        </>}
      </article>;
    })}
  </section>;
  return embedded
    ? <div className="teacher-support-page">{content}{rubricWorkspace}</div>
    : <main className="functional-app"><header className="app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><Link href="/teacher">教材资料</Link><Link href="/teacher/questions">题库审核</Link><strong>测验配置</strong></header><div className="functional-layout"><aside className="functional-nav"><strong>课程</strong>{courses.map(course => <button key={course.id} className={course.id === courseId ? "data-nav active" : "data-nav"} onClick={() => setCourseId(course.id)}>{course.title}</button>)}</aside>{content}</div>{rubricWorkspace}</main>;
}
