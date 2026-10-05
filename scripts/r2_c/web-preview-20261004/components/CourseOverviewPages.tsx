"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";

type Material = { id: string; title: string; current_version: null | { id: string; version_no: number; workflow_state?: string; status: string } };
type Job = { job_id: string; kind: string; status: string; progress: number; material_title?: string };
type Analytics = { participation: { student_count: number; engaged_student_count: number; completed_learning_session_count: number; published_material_count: number }; assessments: { attempt_count: number; participant_count: number; average_score: number | null }; pending_review_task_count: number };
type Assessment = { id: string; title: string; availability: string; ai_policy: string };
type Review = { id: string; reason: string; due_at: string };
type GrowthKnowledge = { knowledge_point: string; state: string; evidence_count: number; next_step: string; updated_at: string };

function message(reason: unknown): string { return reason instanceof ApiError ? reason.message : "暂时无法读取课程信息，请检查服务后重试。"; }
const stateLabel: Record<string, string> = { review_required: "需要处理", failed: "处理失败", parsing: "正在处理", indexing: "正在准备", ready_to_publish: "可以发布", published: "已发布", uploaded: "等待解析" };

export function TeacherCourseOverview() {
  const { courseId } = useParams<{ courseId: string }>();
  const [materials, setMaterials] = useState<Material[]>([]); const [analytics, setAnalytics] = useState<Analytics | null>(null); const [jobs, setJobs] = useState<Job[]>([]); const [notice, setNotice] = useState("正在读取课程概览…");
  useEffect(() => { Promise.all([api<Material[]>(`/courses/${courseId}/materials`), api<Analytics>(`/courses/${courseId}/analytics/overview`), api<Job[]>(`/courses/${courseId}/material-jobs`)]).then(([nextMaterials, nextAnalytics, nextJobs]) => { setMaterials(nextMaterials); setAnalytics(nextAnalytics); setJobs(nextJobs); setNotice(""); }).catch((reason) => setNotice(message(reason))); }, [courseId]);
  const attention = materials.filter((material) => ["review_required", "failed"].includes(material.current_version?.workflow_state ?? material.current_version?.status ?? ""));
  const running = jobs.filter((job) => ["queued", "running"].includes(job.status));
  const base = `/teacher/courses/${courseId}`;
  return <div className="course-overview"><div className="page-heading"><div><h1>课程概览</h1><p>查看课程待处理事项与学习情况；教材、题目和测验仍在各自页面管理。</p></div><Link className="primary-button" href={`${base}/materials`}><Icon icon="solar:book-bookmark-linear" />管理教材</Link></div>{notice && <p className="status-banner">{notice}</p>}
    {!notice && <><section className="attention-panel"><h2>需要关注</h2>{attention.length || running.length ? <div className="attention-list">{attention.map((material) => <Link href={`${base}/materials`} key={material.id}><Icon icon="solar:danger-triangle-linear" /><span><strong>{material.title}</strong><small>{stateLabel[material.current_version?.workflow_state ?? material.current_version?.status ?? ""] ?? "需要处理"}</small></span><Icon icon="solar:arrow-right-linear" /></Link>)}{running.map((job) => <Link href={`${base}/materials#tasks`} key={job.job_id}><Icon icon="solar:hourglass-line-duotone" /><span><strong>{job.material_title ?? "教材处理"}</strong><small>{job.kind === "material_parse" ? "正在解析" : "正在准备学习资料"} · {job.progress}%</small></span><Icon icon="solar:arrow-right-linear" /></Link>)}</div> : <div className="positive-empty"><Icon icon="solar:check-circle-bold" />当前没有需要处理的事项。</div>}</section>
    <section className="course-metrics"><article><strong>{analytics?.participation.student_count ?? 0}</strong><span>在册学生</span></article><article><strong>{analytics?.participation.published_material_count ?? 0}</strong><span>已发布教材</span></article><article><strong>{analytics?.assessments.average_score ?? "—"}</strong><span>测验平均分</span></article><article><strong>{analytics?.pending_review_task_count ?? 0}</strong><span>待完成复习</span></article></section>
    <section className="overview-section"><div className="panel-heading"><h2>教材状态</h2><Link href={`${base}/materials`}>查看全部</Link></div>{materials.length ? materials.slice(0, 5).map((material) => <Link className="overview-row" href={`${base}/materials`} key={material.id}><span><strong>{material.title}</strong><small>{material.current_version ? `版本 ${material.current_version.version_no}` : "暂无版本"}</small></span><em>{stateLabel[material.current_version?.workflow_state ?? material.current_version?.status ?? ""] ?? "草稿"}</em></Link>) : <p className="empty-state">尚未上传教材。上传并发布后，学生才能开始学习。</p>}</section></>}
  </div>;
}

export function StudentCourseHome() {
  const { courseId } = useParams<{ courseId: string }>();
  const [materials, setMaterials] = useState<Material[]>([]); const [assessments, setAssessments] = useState<Assessment[]>([]); const [reviews, setReviews] = useState<Review[]>([]); const [mastery, setMastery] = useState<GrowthKnowledge[]>([]); const [notice, setNotice] = useState("正在读取学习信息…");
  useEffect(() => { Promise.all([api<Material[]>(`/courses/${courseId}/materials`), api<Assessment[]>(`/courses/${courseId}/assessments`), api<Review[]>("/review-tasks?due_only=false"), api<GrowthKnowledge[]>(`/student/growth/knowledge?course_id=${courseId}`)]).then(([nextMaterials, nextAssessments, nextReviews, nextMastery]) => { setMaterials(nextMaterials); setAssessments(nextAssessments); setReviews(nextReviews); setMastery(nextMastery); setNotice(""); }).catch((reason) => setNotice(message(reason))); }, [courseId]);
  const base = `/student/courses/${courseId}`;
  return <div className="course-overview student-home"><div className="page-heading"><div><h1>学习首页</h1><p>从已发布教材出发，完成学习、练习和复习。</p></div></div>{notice && <p className="status-banner">{notice}</p>}{!notice && <><section className="continue-card"><div><span>继续学习</span><h2>{materials[0]?.title ?? "当前还没有可学习的教材"}</h2><p>{materials[0] ? "阅读教材、搜索课程内容，并在证据支持下提问。" : "教师发布教材后，你可以从这里开始学习。"}</p></div>{materials[0] && <Link className="primary-button" href={`${base}/learn`}>进入学习<Icon icon="solar:arrow-right-linear" /></Link>}</section><div className="student-next-grid"><section className="overview-section"><div className="panel-heading"><h2>待复习</h2><Link href={`${base}/practice`}>查看练习</Link></div>{reviews.length ? reviews.slice(0, 4).map((review) => <div className="overview-row" key={review.id}><span><strong>{review.reason}</strong><small>截止：{new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span></div>) : <p className="empty-state">暂无待完成复习。</p>}</section><section className="overview-section"><div className="panel-heading"><h2>开放测验</h2><Link href={`${base}/practice`}>查看练习</Link></div>{assessments.length ? assessments.slice(0, 4).map((assessment) => <div className="overview-row" key={assessment.id}><span><strong>{assessment.title}</strong><small>{assessment.availability}</small></span></div>) : <p className="empty-state">当前没有可参加的测验。</p>}</section></div><section className="overview-section"><div className="panel-heading"><h2>我的知识状态</h2><Link href={`${base}/growth`}>查看成长</Link></div>{mastery.length ? mastery.slice(0, 5).map((item) => <div className="mastery-row" key={item.knowledge_point}><span><strong>{item.knowledge_point}</strong><small>{item.state} · 依据 {item.evidence_count} 条</small></span><em>{item.next_step}</em></div>) : <p className="empty-state">完成学习或测验后，这里会显示你的知识状态。</p>}</section></>}</div>;
}
