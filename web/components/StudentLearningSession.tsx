"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";
import LearningBlockStream from "./learning/LearningBlockStream";
import { appendLearningEvent } from "../lib/learning-events";
import { studentMaterialVersion } from "../lib/student-material-version";
import {
  legacyLearningBlocks,
  normalizeLearningBlocks,
  type LearningBlock,
} from "../lib/learning-blocks";

type Course = { id: string; title: string }; type Material = { id: string; title: string; current_version: null | { id: string; version_no?: number; status: string }; learning_version?: null | { id: string; version_no: number; status: string } }; type Learning = { id: string; task_id?: string; course_id?: string; state: string; state_version: number; task_version?: number; tutor_message: string; message?: string; action?: string; hint_level: number; status?: string; allowed_actions?: string[]; blocks?: LearningBlock[] };
const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "请求失败，请稍后重试。";
export default function StudentLearningSession() {
  const [courses, setCourses] = useState<Course[]>([]); const [courseId, setCourseId] = useState(""); const [materials, setMaterials] = useState<Material[]>([]); const [versionId, setVersionId] = useState(""); const [learning, setLearning] = useState<Learning | null>(null); const [answer, setAnswer] = useState(""); const [notice, setNotice] = useState(""); const [recoveryTaskId, setRecoveryTaskId] = useState<string | null>(null); const [recovering, setRecovering] = useState(false);
  const recoverTask = useCallback(async (taskId: string) => {
    setRecovering(true);
    try {
      const recovered = await api<Learning>(`/student/learning/tasks/${taskId}`);
      setLearning(recovered);
      if (recovered.course_id) setCourseId(recovered.course_id);
      setRecoveryTaskId(null);
      setNotice("");
    } catch (reason) {
      setRecoveryTaskId(taskId);
      setNotice(`${explain(reason)} 已保留当前学习会话标识；网络恢复后可重试恢复。`);
    } finally {
      setRecovering(false);
    }
  }, []);
  useEffect(() => {
    let active = true;
    const saved = window.sessionStorage.getItem("student-learning-task");
    api<Course[]>("/courses").then(data => {
      setCourses(data);
      if (!saved) setCourseId(data[0]?.id ?? "");
    }).catch(reason => setNotice(explain(reason)));
    if (saved) {
      queueMicrotask(() => {
        if (!active) return;
        void recoverTask(saved);
      });
    }
    return () => { active = false; };
  }, [recoverTask]);
  useEffect(() => { if (!courseId) return; api<Material[]>(`/courses/${courseId}/materials`).then(data => { setMaterials(data); setVersionId(data[0] ? studentMaterialVersion(data[0])?.id ?? "" : ""); }).catch(reason => setNotice(explain(reason))); }, [courseId]);
  async function start() { if (!courseId || !versionId) return; try { const session = await api<Learning>("/learning-sessions", { method: "POST", body: JSON.stringify({ course_id: courseId, material_version_id: versionId }) }); setLearning(session); window.sessionStorage.setItem("student-learning-task", session.id); void appendLearningEvent({ event_key: `learning-session-viewed:${session.id}`, course_id: courseId, event_type: "task_viewed", source_type: "tutor", source_ref: session.id, payload: { material_version_id: versionId } }).catch(() => undefined); setNotice(""); } catch (reason) { setNotice(explain(reason)); } }
  async function respond(event: FormEvent) { event.preventDefault(); if (!learning || !answer.trim() || !learning.allowed_actions?.includes("RESPOND_TASK")) return; try { const next = await api<Learning>(`/student/learning/tasks/${learning.id}/respond`, { method: "POST", body: JSON.stringify({ state_version: learning.state_version, content: answer, action: "respond_task" }) }); setLearning(next); setAnswer(""); setNotice(""); } catch (reason) { if (reason instanceof ApiError && reason.code === "RESOURCE_VERSION_CONFLICT") { try { setLearning(await api<Learning>(`/student/learning/tasks/${learning.id}`)); setNotice("学习状态已更新；你的回答仍保留，请确认最新回合后再提交。"); } catch { setNotice(`${explain(reason)} 你的回答仍保留，可重试。`); } } else setNotice(`${explain(reason)} 你的回答仍保留，可重试。`); } }
  async function transitionTask() { if (!learning) return; const paused = learning.status === "paused"; const action = paused ? "resume" : "pause"; try { const next = await api<Learning>(`/student/learning/tasks/${learning.id}/${action}`, { method: "POST", body: JSON.stringify({ state_version: learning.state_version }) }); setLearning(next); setNotice(""); } catch (reason) { setNotice(explain(reason)); } }
  const blocks = learning
    ? (() => {
        const normalized = normalizeLearningBlocks(learning.blocks);
        return normalized.length
          ? normalized
          : legacyLearningBlocks(learning.id, learning.state_version, learning.tutor_message);
      })()
    : [];
  const courseForLearn = learning?.course_id ?? courseId;
  return <main className="functional-app"><header className="app-header learning-app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" /><span>实验心理学智能学习平台</span></Link><Link href="/student">学习首页</Link><strong>引导学习</strong></header><div className="functional-layout"><aside className="functional-nav"><strong>学习材料</strong>{courses.map(course => <button type="button" className={course.id === courseId ? "data-nav active" : "data-nav"} key={course.id} onClick={() => { setCourseId(course.id); setLearning(null); window.sessionStorage.removeItem("student-learning-task"); }}>{course.title}</button>)}{materials.map(material => { const version = studentMaterialVersion(material); return <button type="button" key={material.id} className={version?.id === versionId ? "data-nav active" : "data-nav"} onClick={() => { setVersionId(version?.id ?? ""); setLearning(null); window.sessionStorage.removeItem("student-learning-task"); }}>{material.title}<small>版本 {version?.version_no ?? "—"} · {version?.status ?? "不可用"}</small></button>; })}</aside><section className="functional-main"><div className="section-title"><div><p className="eyebrow">服务端状态机</p><h1>AI 引导学习</h1><p>诊断、提示、讲解和练习状态由服务端控制，前端不自行改变掌握状态。</p></div></div>{notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}{!learning && recoveryTaskId && <section className="data-panel" aria-labelledby="recover-learning-title"><h2 id="recover-learning-title">恢复上一学习会话</h2><p className="empty-state">此处保留上一会话标识；恢复后会读取服务端已保存的进度。网络恢复后可以重试。</p><button className="secondary-button" type="button" onClick={() => void recoverTask(recoveryTaskId)} disabled={recovering}>{recovering ? "正在恢复…" : "重试恢复学习"}</button></section>}{!learning && <section className="data-panel"><h2>开始一个学习会话</h2><p className="empty-state">只能基于已发布且解析成功的教材版本开始学习。</p><button className="primary-button" onClick={() => void start()} disabled={!versionId}>开始学习</button></section>}{learning && <section className="chat-panel"><div className="mini-row"><span><strong>当前阶段：{learning.state}</strong><small>提示等级：{learning.hint_level} · {learning.status ?? "active"}</small></span><span className="inline-actions" style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: 8 }}>{courseForLearn && <Link className="secondary-button" href={`/student/courses/${encodeURIComponent(courseForLearn)}/learn`}>打开课程教材与学习助手</Link>}{learning.allowed_actions?.includes("RESPOND_TASK") || learning.allowed_actions?.includes("RESUME") ? <button className="secondary-button" type="button" onClick={() => void transitionTask()}>{learning.status === "paused" ? "继续学习" : "暂时暂停"}</button> : null}</span></div><LearningBlockStream blocks={blocks} /><form className="composer" onSubmit={respond}><input aria-label="回答当前学习问题" value={answer} onChange={event => setAnswer(event.target.value)} disabled={!learning.allowed_actions?.includes("RESPOND_TASK")} placeholder="回答当前问题或说明你的困难…" /><button type="submit" aria-label="提交学习回答" disabled={!learning.allowed_actions?.includes("RESPOND_TASK")}><Icon icon="solar:plain-2-bold" /></button></form></section>}</section></div></main>;
}
