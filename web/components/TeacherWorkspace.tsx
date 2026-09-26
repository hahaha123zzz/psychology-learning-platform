"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError, idempotencyKey, uploadForm } from "../lib/api";

type Course = { id: string; title: string; term: string; description?: string };
type MaterialVersion = { id: string; version_no: number; status: string; quality_gate_status?: string; workflow_state?: string; published_snapshot_id?: string | null; size_bytes: number };
type Material = { id: string; title: string; material_type: string; status: string; visibility?: string; current_version: MaterialVersion | null };
type Issue = { id: string; severity: string; code: string; detail: unknown; status: string; resolution?: string | null };
type Job = { job_id: string; kind: string; status: string; progress: number; stage?: string | null; error?: string | null; retryable: boolean; material_title?: string; version_no?: number };
type WorkflowStep = { key: "upload" | "parse" | "review" | "index" | "publish"; status: string; progress: number };
type Workflow = { state: string; steps: WorkflowStep[]; allowed_actions: string[]; blockers: { code: string; message: string }[]; issue_counts: { blocking_open: number; warning_open: number; info_open: number; resolved: number }; indexed_chunk_count: number; embedding_version?: string | null; parse_job?: Job | null; index_job?: Job | null; publication?: { id: string; embedding_version: string; published_at: string } | null };
type Analytics = { participation: { student_count: number; engaged_student_count: number; completed_learning_session_count: number; published_material_count: number }; assessments: { attempt_count: number; participant_count: number; average_score: number | null }; pending_review_task_count: number };

const FLOW_LABELS: Record<WorkflowStep["key"], string> = { upload: "上传", parse: "解析", review: "教师审核", index: "构建索引", publish: "发布" };
const STATE_LABELS: Record<string, string> = { uploading: "上传中", uploaded: "等待解析", parsing: "正在解析", review_required: "需要审核", index_required: "等待构建索引", indexing: "正在构建索引", ready_to_publish: "可以发布", published: "已发布", failed: "处理失败" };
const STAGE_LABELS: Record<string, string> = { queued: "排队中", download: "读取教材", parse: "提取文本与版面", quality: "质量检查", persist: "保存解析结果", chunk: "构建检索单元", embed: "生成索引", done: "已完成" };

function describeError(reason: unknown): string {
  if (!(reason instanceof ApiError)) return "请求未完成，请检查本地服务与登录状态。";
  const suffix = reason.code ? `（${reason.code}）` : "";
  return `${reason.message}${suffix}${reason.retryable ? "，可以重试。" : ""}`;
}

function formatIssueDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "count" in detail && typeof detail.count === "number") return `检测到 ${detail.count} 项，请核对后处理。`;
  if (detail && typeof detail === "object") return Object.entries(detail).map(([key, value]) => `${key}: ${String(value)}`).join("；");
  return "解析器返回了质量问题，请核对。";
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.ceil(bytes / 1024)} KB`;
}

export default function TeacherWorkspace() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selected, setSelected] = useState<Material | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [notice, setNotice] = useState("正在读取教师课程…");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [busyAction, setBusyAction] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const loadCourses = useCallback(async () => {
    try {
      const list = await api<Course[]>("/courses");
      setCourses(list);
      setCourseId(current => current || list[0]?.id || "");
      setNotice(list.length ? "" : "尚无课程，可先创建课程。");
    } catch (reason) { setNotice(describeError(reason)); }
  }, []);

  const loadCourse = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const [list, overview, taskList] = await Promise.all([
        api<Material[]>(`/courses/${id}/materials`),
        api<Analytics>(`/courses/${id}/analytics/overview`),
        api<Job[]>(`/courses/${id}/material-jobs`),
      ]);
      setMaterials(list);
      setAnalytics(overview);
      setJobs(taskList);
      setSelected(current => list.find(item => item.id === current?.id) ?? list[0] ?? null);
    } catch (reason) { setNotice(describeError(reason)); }
  }, []);

  const loadVersion = useCallback(async (versionId: string) => {
    const [nextWorkflow, nextIssues] = await Promise.all([
      api<Workflow>(`/material-versions/${versionId}/workflow`),
      api<Issue[]>(`/material-versions/${versionId}/review-issues`),
    ]);
    setWorkflow(nextWorkflow);
    setIssues(nextIssues);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadCourses(), 0);
    return () => window.clearTimeout(timer);
  }, [loadCourses]);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadCourse(courseId), 0);
    return () => window.clearTimeout(timer);
  }, [courseId, loadCourse]);
  useEffect(() => {
    const versionId = selected?.current_version?.id;
    const timer = window.setTimeout(() => {
      if (!versionId) { setWorkflow(null); setIssues([]); return; }
      void loadVersion(versionId).catch(reason => setNotice(describeError(reason)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selected?.current_version?.id, loadVersion]);
  useEffect(() => {
    if (!jobs.some(job => job.status === "queued" || job.status === "running")) return;
    const timer = window.setInterval(() => {
      void loadCourse(courseId);
      const versionId = selected?.current_version?.id;
      if (versionId) void loadVersion(versionId).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [jobs, courseId, selected?.current_version?.id, loadCourse, loadVersion]);
  useEffect(() => {
    if (!uploading) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  async function createCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fd = new FormData(event.currentTarget);
    try {
      const course = await api<Course>("/courses", { method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify({ title: fd.get("title"), term: fd.get("term"), description: fd.get("description") || null, timezone: "Asia/Shanghai" }) });
      setCourses(items => [course, ...items]); setCourseId(course.id); setShowCreate(false); setNotice("课程已创建。");
    } catch (reason) { setNotice(describeError(reason)); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!courseId) return;
    const form = event.currentTarget;
    const fd = new FormData(form);
    const file = fd.get("file");
    if (!(file instanceof File) || !file.size) { setNotice("请选择 PDF 或 DOCX 文件。"); return; }
    const body = new FormData();
    body.set("title", String(fd.get("title") || file.name));
    body.set("material_type", "textbook"); body.set("visibility", "draft"); body.set("file", file);
    setUploading(true); setUploadProgress(0); setNotice(`正在上传 ${file.name}，上传期间请不要关闭页面。`);
    try {
      await uploadForm(`/courses/${courseId}/materials`, body, setUploadProgress);
      form.reset(); setNotice("教材上传完成，下一步可以开始解析。"); await loadCourse(courseId);
    } catch (reason) { setNotice(describeError(reason)); }
    finally { setUploading(false); }
  }

  async function runAction(path: string, label: string) {
    try {
      setBusyAction(label); setNotice(`${label}请求已提交…`);
      const data = await api<{ job_id?: string; publication_snapshot_id?: string }>(path, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() } });
      setNotice(data.job_id ? `${label}任务已进入后台，可以切换页面后再回来查看。` : `${label}完成，学生端将在刷新后使用当前教材。`);
      await loadCourse(courseId);
      if (selected?.current_version?.id) await loadVersion(selected.current_version.id);
    } catch (reason) { setNotice(describeError(reason)); }
    finally { setBusyAction(""); }
  }

  async function resolve(issue: Issue) {
    const resolution = window.prompt("填写处理说明：");
    if (!resolution) return;
    try {
      await api(`/parse-review-issues/${issue.id}`, { method: "PATCH", body: JSON.stringify({ status: "resolved", resolution }) });
      if (selected?.current_version?.id) await loadVersion(selected.current_version.id);
      setNotice("审核问题已处理。");
    } catch (reason) { setNotice(describeError(reason)); }
  }

  const version = selected?.current_version;
  const activeJob = workflow?.parse_job?.status === "running" || workflow?.parse_job?.status === "queued" ? workflow.parse_job : workflow?.index_job?.status === "running" || workflow?.index_job?.status === "queued" ? workflow.index_job : null;
  const primaryAction = useMemo(() => workflow?.allowed_actions[0] ?? "", [workflow]);

  function primaryButton() {
    if (!version || !primaryAction) return null;
    if (primaryAction === "start_parse" || primaryAction === "retry_parse") return <button className="primary-button" disabled={Boolean(busyAction)} onClick={() => void runAction(`/material-versions/${version.id}/parse`, primaryAction === "retry_parse" ? "重试解析" : "开始解析")}><Icon icon="solar:document-add-linear" />{primaryAction === "retry_parse" ? "重试解析" : "开始解析"}</button>;
    if (primaryAction === "build_index") return <button className="primary-button" disabled={Boolean(busyAction)} onClick={() => void runAction(`/material-versions/${version.id}/embed`, "构建索引")}><Icon icon="solar:database-linear" />构建候选索引</button>;
    if (primaryAction === "publish") return <button className="primary-button" disabled={Boolean(busyAction)} onClick={() => void runAction(`/material-versions/${version.id}/publish`, "发布")}><Icon icon="solar:upload-linear" />发布给学生</button>;
    if (primaryAction === "review_issues") return <a className="primary-button" href="#review-issues"><Icon icon="solar:shield-check-linear" />处理审核问题</a>;
    return null;
  }

  return <main className="functional-app">
    <header className="app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><span>教师工作台 · 教材发布</span></header>
    <div className="functional-layout">
      <aside className="functional-nav"><strong>课程</strong><button className="primary-button" onClick={() => setShowCreate(true)}><Icon icon="solar:add-circle-linear" />新建课程</button>{courses.map(course => <button key={course.id} className={course.id === courseId ? "data-nav active" : "data-nav"} onClick={() => setCourseId(course.id)}>{course.title}<small>{course.term}</small></button>)}</aside>
      <section className="functional-main ingestion-workspace">
        <div className="section-title"><div><p className="eyebrow">教材摄取流水线</p><h1>教材资料与发布</h1><p>{courses.find(course => course.id === courseId)?.description || "上传、解析、审核、构建索引后，再发布给学生。"}</p></div><span className={`workflow-state ${workflow?.state ?? "idle"}`}>{workflow ? STATE_LABELS[workflow.state] ?? workflow.state : "请选择教材"}</span></div>
        {notice && <p className="status-banner"><Icon icon="solar:info-circle-linear" />{notice}</p>}
        {showCreate && <form className="inline-form" onSubmit={createCourse}><input name="title" placeholder="课程名称" required /><input name="term" placeholder="学期，例如 2026 秋" required /><input name="description" placeholder="课程说明（可选）" /><button className="primary-button">创建</button><button type="button" onClick={() => setShowCreate(false)}>取消</button></form>}
        {workflow && <ol className="workflow-steps">{workflow.steps.map((step, index) => <li key={step.key} className={step.status}><span>{step.status === "completed" ? <Icon icon="solar:check-circle-bold" /> : index + 1}</span><div><strong>{FLOW_LABELS[step.key]}</strong><small>{step.status === "completed" ? "已完成" : step.status === "current" ? `${step.progress}%` : step.status === "blocked" ? "需处理" : "未开始"}</small></div></li>)}</ol>}
        {courseId && <form className="upload-card" onSubmit={upload}><div><strong><Icon icon="solar:cloud-upload-linear" />上传新教材</strong><p>支持 PDF、DOCX，单文件最大 200MB。当前版本上传中离开页面会中断。</p></div><input name="title" placeholder="资料名称（默认使用文件名）" /><input name="file" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={uploading} required /><button className="primary-button" disabled={uploading}>{uploading ? `上传中 ${uploadProgress}%` : "上传教材"}</button>{uploading && <div className="upload-progress" aria-label={`上传进度 ${uploadProgress}%`}><span style={{ width: `${uploadProgress}%` }} /></div>}</form>}
        <div className="ingestion-grid">
          <section className="data-panel material-list-panel"><h2>教材版本</h2>{materials.length ? materials.map(item => <button className={selected?.id === item.id ? "material-row selected" : "material-row"} key={item.id} onClick={() => setSelected(item)}><span><strong>{item.title}</strong><small>{item.current_version ? `v${item.current_version.version_no} · ${formatBytes(item.current_version.size_bytes)}` : "无版本"}</small></span><em>{STATE_LABELS[item.current_version?.workflow_state ?? ""] ?? item.current_version?.status ?? item.status}</em></button>) : <p className="empty-state">暂无资料。上传 PDF 或 DOCX 后会显示在这里。</p>}</section>
          <section className="data-panel workflow-panel"><h2>当前教材</h2>{selected && version && workflow ? <><div className="material-heading"><div><strong>{selected.title}</strong><small>版本 v{version.version_no} · {formatBytes(version.size_bytes)}</small></div><span className={`workflow-state ${workflow.state}`}>{STATE_LABELS[workflow.state] ?? workflow.state}</span></div>{activeJob && <div className="live-progress"><div><strong>{activeJob.kind === "material_parse" ? "教材解析" : "索引构建"}</strong><span>{STAGE_LABELS[activeJob.stage ?? ""] ?? activeJob.stage ?? "处理中"} · {activeJob.progress}%</span></div><progress value={activeJob.progress} max="100" /><small>任务在当前服务进程中后台执行，可切换页面后回来查看。</small></div>}<dl className="data-details"><dt>质量门禁</dt><dd>{version.quality_gate_status ?? "pending"}</dd><dt>检索单元</dt><dd>{workflow.indexed_chunk_count} 个已索引 Chunk</dd><dt>模型版本</dt><dd>{workflow.embedding_version ?? "配置不可用"}</dd><dt>学生可见</dt><dd>{workflow.state === "published" ? "是" : "否，完成全部门禁后才可见"}</dd></dl>{workflow.blockers.length > 0 && <div className="blocker-list">{workflow.blockers.map(blocker => <p key={`${blocker.code}-${blocker.message}`}><Icon icon={blocker.code === "QUALITY_WARNING" ? "solar:danger-triangle-linear" : "solar:close-circle-linear"} /><span><strong>{blocker.code}</strong>{blocker.message}</span></p>)}</div>}<div className="primary-action-area">{primaryButton()}{!primaryAction && activeJob && <span className="processing-label"><i />后台处理中，请稍候</span>}{workflow.state === "published" && <span className="published-message"><Icon icon="solar:verified-check-bold" />已发布，学生刷新后即可使用</span>}</div>{workflow.publication && <p className="snapshot-line">发布快照 {workflow.publication.id.slice(-8)} · {new Date(workflow.publication.published_at).toLocaleString("zh-CN")}</p>}</> : <p className="empty-state">选择一个教材版本，查看当前阶段和下一步操作。</p>}</section>
        </div>
        <div className="ingestion-grid secondary-grid">
          <section className="data-panel" id="review-issues"><div className="panel-title"><h2>选择性审核</h2>{workflow && <span>阻塞 {workflow.issue_counts.blocking_open} · 警告 {workflow.issue_counts.warning_open} · 已处理 {workflow.issue_counts.resolved}</span>}</div>{issues.length ? issues.map(issue => <div className={`issue-line ${issue.severity}`} key={issue.id}><Icon icon={issue.status !== "open" ? "solar:check-circle-linear" : issue.severity === "blocking" ? "solar:close-circle-linear" : "solar:danger-triangle-linear"} /><span><strong>{issue.code}</strong><small>{formatIssueDetail(issue.detail)}</small></span><em>{issue.severity} · {issue.status}</em>{issue.status === "open" && issue.severity !== "blocking" ? <button onClick={() => void resolve(issue)}>确认处理</button> : null}</div>) : <p className="empty-state">当前版本没有解析审核问题。</p>}</section>
          <section className="data-panel task-center"><div className="panel-title"><h2>后台任务</h2><button onClick={() => void loadCourse(courseId)}><Icon icon="solar:refresh-linear" />刷新</button></div>{jobs.length ? jobs.slice(0, 8).map(job => <article key={job.job_id}><div><strong>{job.kind === "material_parse" ? "解析" : "索引"} · {job.material_title}</strong><small>v{job.version_no} · {STAGE_LABELS[job.stage ?? ""] ?? job.stage ?? job.status}</small></div><span className={`task-status ${job.status}`}>{job.status === "running" || job.status === "queued" ? `${job.progress}%` : job.status === "succeeded" ? "完成" : "失败"}</span>{(job.status === "running" || job.status === "queued") && <progress value={job.progress} max="100" />}{job.error && <p>{job.error}{job.retryable ? "（可以重试）" : ""}</p>}</article>) : <p className="empty-state">当前课程暂无解析或索引任务。</p>}</section>
        </div>
        {analytics && <section className="analytics-strip"><div><strong>{analytics.participation.student_count}</strong><span>在册学生</span></div><div><strong>{analytics.participation.engaged_student_count}</strong><span>参与学习</span></div><div><strong>{analytics.participation.published_material_count}</strong><span>已发布资料</span></div><div><strong>{analytics.assessments.average_score ?? "—"}</strong><span>测验平均分</span></div><div><strong>{analytics.pending_review_task_count}</strong><span>待复习任务</span></div></section>}
      </section>
    </div>
  </main>;
}
