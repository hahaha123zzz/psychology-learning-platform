"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { api, ApiError, idempotencyKey, uploadMaterialResumable } from "../lib/api";

type MaterialVersion = { id: string; version_no: number; status: string; workflow_state?: string; quality_gate_status?: string; size_bytes: number };
type Material = { id: string; title: string; material_type: string; current_version: MaterialVersion | null };
type Job = { job_id: string; kind: string; status: string; progress: number; stage?: string | null; error?: string | null; retryable: boolean; material_title?: string; version_no?: number; checkpoint?: { completed_pages?: number; total_pages?: number } | null };
type Issue = { id: string; severity: string; code: string; detail: unknown; status: string };
type Workflow = { state: string; allowed_actions: string[]; blockers: { code: string; message: string }[]; issue_counts: { blocking_open: number; warning_open: number; info_open: number; resolved: number }; steps: { key: "upload" | "parse" | "review" | "index" | "publish"; status: string; progress: number }[]; parse_job?: Job | null; index_job?: Job | null };

const STATE: Record<string, string> = { uploading: "上传中", uploaded: "等待解析", parsing: "正在处理", review_required: "需要处理", index_required: "等待准备", indexing: "正在准备", ready_to_publish: "可以发布", published: "已发布", failed: "处理失败" };
const STEP: Record<string, string> = { upload: "上传", parse: "解析", review: "审核", index: "准备学习资料", publish: "发布" };
const STAGE: Record<string, string> = { queued: "排队中", download: "读取教材", parse: "解析教材", parse_pages: "逐页解析", quality: "检查内容", persist: "保存结果", chunk: "准备学习资料", embed: "准备学习资料", done: "已完成" };

function explain(reason: unknown): string { return reason instanceof ApiError ? `${reason.message}${reason.retryable ? "，可以重试。" : ""}` : "请求未完成，请检查本地服务与登录状态。"; }
function bytes(value: number): string { return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`; }
function issueText(detail: unknown): string { if (typeof detail === "string") return detail; if (detail && typeof detail === "object" && "count" in detail && typeof detail.count === "number") return `检测到 ${detail.count} 项内容，请核对后处理。`; return "系统发现该教材存在需要关注的内容。"; }

export default function TeacherMaterialsPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const [materials, setMaterials] = useState<Material[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [notice, setNotice] = useState("正在读取教材…");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const selected = useMemo(() => materials.find((material) => material.id === selectedId) ?? null, [materials, selectedId]);
  const version = selected?.current_version;

  const loadCourse = useCallback(async () => {
    if (!courseId) return;
    try {
      const [nextMaterials, nextJobs] = await Promise.all([api<Material[]>(`/courses/${courseId}/materials`), api<Job[]>(`/courses/${courseId}/material-jobs`)]);
      setMaterials(nextMaterials);
      setJobs(nextJobs);
      setSelectedId((current) => nextMaterials.some((item) => item.id === current) ? current : nextMaterials[0]?.id ?? "");
      setNotice((current) => current === "正在读取教材…" ? "" : current);
    } catch (reason) { setNotice(explain(reason)); }
  }, [courseId]);

  const loadVersion = useCallback(async (versionId: string) => {
    try {
      const [nextWorkflow, nextIssues] = await Promise.all([api<Workflow>(`/material-versions/${versionId}/workflow`), api<Issue[]>(`/material-versions/${versionId}/review-issues`)]);
      setWorkflow(nextWorkflow); setIssues(nextIssues);
    } catch (reason) { setNotice(explain(reason)); }
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => { void loadCourse(); }, 0); return () => window.clearTimeout(timer); }, [loadCourse]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (version?.id) void loadVersion(version.id);
      else { setWorkflow(null); setIssues([]); }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [version?.id, loadVersion]);
  useEffect(() => {
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) return;
    const timer = window.setInterval(() => { void loadCourse(); if (version?.id) void loadVersion(version.id); }, 1500);
    return () => window.clearInterval(timer);
  }, [jobs, loadCourse, loadVersion, version?.id]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget; const formData = new FormData(form); const file = formData.get("file");
    if (!(file instanceof File) || !file.size) { setNotice("请选择 PDF 或 DOCX 文件。 "); return; }
    setUploading(true); setUploadProgress(0); setNotice(`正在准备 ${file.name}；若中断，重新选择同一文件即可继续。`);
    try {
      await uploadMaterialResumable(courseId, { title: String(formData.get("title") || file.name), material_type: "textbook", file }, (percent, detail) => { setUploadProgress(percent); setNotice(detail); });
      form.reset(); setNotice("教材上传完成。请选择“开始解析”继续处理。"); await loadCourse();
    } catch (reason) { setNotice(explain(reason)); } finally { setUploading(false); }
  }

  async function action() {
    if (!version || !workflow) return;
    const current = workflow.allowed_actions[0];
    const actionMap: Record<string, { path: string; label: string }> = {
      start_parse: { path: `/material-versions/${version.id}/parse`, label: "开始解析" }, retry_parse: { path: `/material-versions/${version.id}/parse`, label: "重新解析" }, build_index: { path: `/material-versions/${version.id}/embed`, label: "准备学习资料" }, publish: { path: `/material-versions/${version.id}/publish`, label: "发布给学生" },
    };
    const definition = actionMap[current];
    if (!definition) return;
    try {
      setBusy(true); setNotice(`${definition.label}请求已提交…`);
      const result = await api<{ job_id?: string }>(definition.path, { method: "POST", headers: { "Idempotency-Key": idempotencyKey() } });
      setNotice(result.job_id ? `${definition.label}已在后台开始，可以切换页面后再回来查看。` : "教材已发布，学生刷新后即可学习。");
      await loadCourse(); await loadVersion(version.id);
    } catch (reason) { setNotice(explain(reason)); } finally { setBusy(false); }
  }

  const primary = workflow?.allowed_actions[0];
  const primaryLabel: Record<string, string> = { start_parse: "开始解析", retry_parse: "重新解析", build_index: "准备学习资料", publish: "发布给学生" };
  return <div className="materials-page">
    <div className="page-heading"><div><h1>教材</h1><p>上传课程资料，核对处理结果；教材发布后，学生才能在学习空间中使用。</p></div></div>
    {notice && <p className="status-banner"><Icon icon="solar:info-circle-linear" />{notice}</p>}
    <form className="material-upload-panel" onSubmit={upload}>
      <div className="upload-panel-copy"><Icon icon="solar:cloud-upload-linear" /><div><strong>上传教材</strong><p>支持 PDF、DOCX，单个文件最大 200 MB。上传中断后可继续。</p></div></div>
      <input name="title" placeholder="资料名称（默认使用文件名）" disabled={uploading} />
      <input name="file" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={uploading} required />
      <button className="primary-button" disabled={uploading}>{uploading ? `上传中 ${uploadProgress}%` : "上传教材"}</button>
      {uploading && <div className="material-upload-progress"><span style={{ width: `${uploadProgress}%` }} /></div>}
    </form>
    <div className="materials-layout">
      <section className="materials-list"><div className="panel-heading"><h2>课程教材</h2><span>{materials.length} 份</span></div>{materials.length ? materials.map((material) => <button key={material.id} className={material.id === selectedId ? "material-list-row active" : "material-list-row"} onClick={() => setSelectedId(material.id)}><span><strong>{material.title}</strong><small>{material.current_version ? `版本 ${material.current_version.version_no} · ${bytes(material.current_version.size_bytes)}` : "尚未上传版本"}</small></span><em className={`status-tag ${material.current_version?.workflow_state ?? material.current_version?.status ?? "draft"}`}>{STATE[material.current_version?.workflow_state ?? material.current_version?.status ?? ""] ?? "草稿"}</em></button>) : <p className="empty-state">暂无教材。上传 PDF 或 DOCX 后将在这里显示。</p>}</section>
      <section className="material-detail">{selected && version && workflow ? <>
        <div className="material-detail-heading"><div><span className="detail-overline">当前教材</span><h2>{selected.title}</h2><p>版本 {version.version_no} · {bytes(version.size_bytes)}</p></div><span className={`status-tag ${workflow.state}`}>{STATE[workflow.state] ?? workflow.state}</span></div>
        <ol className="material-stepper">{workflow.steps.map((step, index) => <li className={step.status} key={step.key}><span>{step.status === "completed" ? <Icon icon="solar:check-circle-bold" /> : index + 1}</span><strong>{STEP[step.key]}</strong><small>{step.status === "current" ? `${step.progress}%` : step.status === "completed" ? "已完成" : step.status === "blocked" ? "需处理" : "未开始"}</small></li>)}</ol>
        {workflow.blockers.length > 0 && <div className="material-blockers">{workflow.blockers.map((blocker) => <article key={`${blocker.code}-${blocker.message}`}><Icon icon="solar:danger-triangle-linear" /><div><strong>{blocker.code === "QUALITY_WARNING" ? "教材需要核对" : "当前无法继续"}</strong><p>{blocker.message}</p></div></article>)}</div>}
        <section className="material-next-action"><div><strong>{primary === "review_issues" ? "有内容需要你的关注" : workflow.state === "published" ? "教材已发布" : "下一步"}</strong><p>{primary === "review_issues" ? "处理已发现的问题后，才能继续准备并发布教材。" : workflow.state === "published" ? "学生端将只显示这个已发布版本。" : "按当前状态完成下一步，系统会在后台持续处理。"}</p></div>{primary === "review_issues" ? <Link className="primary-button" href="#material-issues">查看问题</Link> : primary && <button className="primary-button" disabled={busy} onClick={() => void action()}>{primaryLabel[primary] ?? "继续"}</button>}</section>
      </> : <div className="material-no-selection"><Icon icon="solar:book-2-linear" /><p>选择一份教材，查看它的处理状态和下一步操作。</p></div>}</section>
    </div>
    <div className="material-support-grid">
      <section className="support-panel" id="material-issues"><div className="panel-heading"><h2>教材问题</h2>{workflow && <span>待处理 {workflow.issue_counts.blocking_open + workflow.issue_counts.warning_open}</span>}</div>{issues.length ? issues.map((issue) => <article className="material-issue" key={issue.id}><Icon icon={issue.severity === "blocking" ? "solar:close-circle-linear" : "solar:danger-triangle-linear"} /><div><strong>{issue.code}</strong><p>{issueText(issue.detail)}</p></div><span>{issue.status === "open" ? "待处理" : "已处理"}</span></article>) : <p className="empty-state">当前教材没有需要处理的问题。</p>}</section>
      <section className="support-panel" id="tasks"><div className="panel-heading"><h2>处理进度</h2><button onClick={() => void loadCourse()}><Icon icon="solar:refresh-linear" />刷新</button></div>{jobs.length ? jobs.slice(0, 8).map((job) => <article className="job-row" key={job.job_id}><div><strong>{job.kind === "material_parse" ? "解析教材" : "准备学习资料"} · {job.material_title}</strong><small>{STAGE[job.stage ?? ""] ?? job.stage ?? job.status}{job.version_no ? ` · 版本 ${job.version_no}` : ""}</small>{job.status === "running" || job.status === "queued" ? <progress value={job.progress} max="100" /> : null}{job.checkpoint?.total_pages && <small>已完成第 {job.checkpoint.completed_pages ?? 0}/{job.checkpoint.total_pages} 页</small>}{job.error && <small className="job-error">{job.error}</small>}</div><span className={`job-state ${job.status}`}>{job.status === "running" || job.status === "queued" ? `${job.progress}%` : job.status === "succeeded" ? "完成" : "失败"}</span></article>) : <p className="empty-state">当前课程没有正在处理的教材任务。</p>}</section>
    </div>
  </div>;
}
