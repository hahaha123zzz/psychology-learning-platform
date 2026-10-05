"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../lib/api";
import LearningBlockStream from "./learning/LearningBlockStream";
import { appendLearningEvent } from "../lib/learning-events";
import {
  legacyLearningBlocks,
  normalizeLearningBlocks,
  type LearningBlock,
} from "../lib/learning-blocks";

type Course = { id: string; title: string }; type Material = { id: string; title: string; current_version: null | { id: string; status: string } }; type Learning = { id: string; task_id?: string; course_id?: string; state: string; state_version: number; task_version?: number; tutor_message: string; message?: string; action?: string; hint_level: number; status?: string; allowed_actions?: string[]; blocks?: LearningBlock[] };
const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "请求失败，请稍后重试。";
export default function StudentLearningSession() {
  const [courses, setCourses] = useState<Course[]>([]); const [courseId, setCourseId] = useState(""); const [materials, setMaterials] = useState<Material[]>([]); const [versionId, setVersionId] = useState(""); const [learning, setLearning] = useState<Learning | null>(null); const [answer, setAnswer] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => {
    const saved = window.sessionStorage.getItem("student-learning-task");
    api<Course[]>("/courses").then(data => {
      setCourses(data);
      if (!saved) setCourseId(data[0]?.id ?? "");
    }).catch(reason => setNotice(explain(reason)));
    void (async () => {
      if (!saved) return;
      try {
        const recovered = await api<Learning>(`/student/learning/tasks/${saved}`);
        setLearning(recovered);
        if (recovered.course_id) setCourseId(recovered.course_id);
        setNotice("");
      } catch {
        window.sessionStorage.removeItem("student-learning-task");
      }
    })();
  }, []);
  useEffect(() => { if (!courseId) return; api<Material[]>(`/courses/${courseId}/materials`).then(data => { setMaterials(data); setVersionId(data[0]?.current_version?.id ?? ""); }).catch(reason => setNotice(explain(reason))); }, [courseId]);
  async function start() { if (!courseId || !versionId) return; try { const session = await api<Learning>("/learning-sessions", { method: "POST", body: JSON.stringify({ course_id: courseId, material_version_id: versionId }) }); setLearning(session); window.sessionStorage.setItem("student-learning-task", session.id); void appendLearningEvent({ event_key: `learning-session-viewed:${session.id}`, course_id: courseId, event_type: "task_viewed", source_type: "tutor", source_ref: session.id, payload: { material_version_id: versionId } }).catch(() => undefined); setNotice(""); } catch (reason) { setNotice(explain(reason)); } }
  async function respond(event: FormEvent) { event.preventDefault(); if (!learning || !answer.trim() || !learning.allowed_actions?.includes("RESPOND_TASK")) return; try { const next = await api<Learning>(`/student/learning/tasks/${learning.id}/respond`, { method: "POST", body: JSON.stringify({ state_version: learning.state_version, content: answer, action: "respond_task" }) }); setLearning(next); setAnswer(""); } catch (reason) { if (reason instanceof ApiError && reason.code === "RESOURCE_VERSION_CONFLICT") { try { setLearning(await api<Learning>(`/student/learning/tasks/${learning.id}`)); setNotice("学习状态已更新，已恢复最新回合，请重新确认你的回答。"); } catch { setNotice(explain(reason)); } } else setNotice(explain(reason)); } }
  async function transitionTask() { if (!learning) return; const paused = learning.status === "paused"; const action = paused ? "resume" : "pause"; try { const next = await api<Learning>(`/student/learning/tasks/${learning.id}/${action}`, { method: "POST", body: JSON.stringify({ state_version: learning.state_version }) }); setLearning(next); setNotice(""); } catch (reason) { setNotice(explain(reason)); } }
  const blocks = learning
    ? (() => {
        const normalized = normalizeLearningBlocks(learning.blocks);
        return normalized.length
          ? normalized
          : legacyLearningBlocks(learning.id, learning.state_version, learning.tutor_message);
      })()
    : [];
  return <main className="functional-app"><header className="app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><Link href="/student">学习首页</Link><strong>引导学习</strong></header><div className="functional-layout"><aside className="functional-nav"><strong>学习材料</strong>{courses.map(course => <button className={course.id === courseId ? "data-nav active" : "data-nav"} key={course.id} onClick={() => { setCourseId(course.id); setLearning(null); window.sessionStorage.removeItem("student-learning-task"); }}>{course.title}</button>)}{materials.map(material => <button key={material.id} className={material.current_version?.id === versionId ? "data-nav active" : "data-nav"} onClick={() => { setVersionId(material.current_version?.id ?? ""); setLearning(null); window.sessionStorage.removeItem("student-learning-task"); }}>{material.title}<small>{material.current_version?.status}</small></button>)}</aside><section className="functional-main"><div className="section-title"><div><p className="eyebrow">服务端状态机</p><h1>AI 引导学习</h1><p>诊断、提示、讲解和练习状态由服务端控制，前端不自行改变掌握状态。</p></div></div>{notice && <p className="status-banner">{notice}</p>}{!learning && <section className="data-panel"><h2>开始一个学习会话</h2><p className="empty-state">只能基于已发布且解析成功的教材版本开始学习。</p><button className="primary-button" onClick={() => void start()} disabled={!versionId}>开始学习</button></section>}{learning && <section className="chat-panel"><div className="mini-row"><span><strong>当前阶段：{learning.state}</strong><small>提示等级：{learning.hint_level} · {learning.status ?? "active"}</small></span>{learning.allowed_actions?.includes("RESPOND_TASK") || learning.allowed_actions?.includes("RESUME") ? <button className="secondary-button" type="button" onClick={() => void transitionTask()}>{learning.status === "paused" ? "继续学习" : "暂时暂停"}</button> : null}</div><LearningBlockStream blocks={blocks} /><form className="composer" onSubmit={respond}><input value={answer} onChange={event => setAnswer(event.target.value)} disabled={!learning.allowed_actions?.includes("RESPOND_TASK")} placeholder="回答当前问题或说明你的困难…" /><button type="submit" disabled={!learning.allowed_actions?.includes("RESPOND_TASK")}><Icon icon="solar:plain-2-bold" /></button></form></section>}</section></div></main>;
}
