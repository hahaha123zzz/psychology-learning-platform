"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import {
  createIntervention,
  dispatchIntervention,
  evaluateIntervention,
  listInterventionRuns,
  listInterventions,
  scheduleIntervention,
  transitionIntervention,
  type Intervention,
  type InterventionActivity,
} from "../lib/interventions-api";
import { ApiError } from "../lib/api";

const explain = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "干预操作未完成，请稍后重试。";

export default function TeacherInterventionsPanel({ courseId }: { courseId: string }) {
  const [items, setItems] = useState<Intervention[]>([]);
  const [students, setStudents] = useState<{ user_id: string; display_name: string; role: string; status: string }[]>([]);
  const [runCounts, setRunCounts] = useState<Record<string, number>>({});
  const [notice, setNotice] = useState("正在读取干预活动…");
  const load = useCallback(() => {
    return Promise.all([
      listInterventions(courseId),
      api<{ user_id: string; display_name: string; role: string; status: string }[]>(`/courses/${courseId}/members`),
    ])
      .then(async ([next, members]) => {
        setItems(next);
        setStudents(members.filter((member) => member.role === "student" && member.status === "active"));
        const pairs = await Promise.all(next.map(async (item) => [item.id, (await listInterventionRuns(courseId, item.id)).length] as const));
        setRunCounts(Object.fromEntries(pairs));
        setNotice("");
      })
      .catch((reason) => setNotice(explain(reason)));
  }, [courseId]);
  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await createIntervention(courseId, {
        title: String(form.get("title")),
        activity_type: String(form.get("activity_type")) as InterventionActivity,
        class_id: null,
        target_snapshot: { knowledge_point: String(form.get("knowledge_point")) },
        plan: { mode: "teacher_assigned", source: "analytics" },
      });
      formElement.reset();
      setNotice("干预草稿已保存；完成目标快照确认后再排程。 ");
      await load();
    } catch (reason) {
      setNotice(explain(reason));
    }
  }

  async function action(item: Intervention, actionName: "schedule" | "start" | "complete" | "evaluate") {
    try {
      const next = actionName === "schedule"
        ? await scheduleIntervention(courseId, item)
        : actionName === "evaluate"
          ? await evaluateIntervention(courseId, item, { immediate_check: "teacher_recorded" })
          : await transitionIntervention(courseId, item, actionName);
      setItems((current) => current.map((candidate) => candidate.id === next.id ? next : candidate));
      setNotice(`干预已更新为${next.status}；完成状态不会直接改变掌握度。`);
    } catch (reason) {
      setNotice(explain(reason));
    }
  }

  async function dispatch(event: FormEvent<HTMLFormElement>, item: Intervention) {
    event.preventDefault();
    const userId = String(new FormData(event.currentTarget).get("user_id") ?? "");
    if (!userId) return;
    try {
      const result = await dispatchIntervention(courseId, item, [userId]);
      setItems((current) => current.map((candidate) => candidate.id === item.id ? result.intervention : candidate));
      setRunCounts((current) => ({ ...current, [item.id]: result.runs.length }));
      setNotice("干预已派发；学生执行完成不会直接改变掌握度。 ");
    } catch (reason) {
      setNotice(explain(reason));
    }
  }

  return <section className="support-panel teacher-list"><div className="panel-heading"><h2>干预活动</h2><span>{items.length} 个</span></div>{notice && <p className="status-banner">{notice}</p>}<form className="support-form" onSubmit={create}><input name="title" placeholder="干预标题" required /><input name="knowledge_point" placeholder="目标知识点" required /><select name="activity_type" defaultValue="reteach"><option value="reteach">再讲解</option><option value="practice_set">练习集</option><option value="mini_lab">Mini Lab</option><option value="discussion">讨论</option><option value="review">复习</option></select><button className="primary-button">保存草稿</button></form>{items.length ? items.map((item) => <article className="teacher-row" key={item.id}><div><span className={`status-tag ${item.status}`}>{item.status}</span><strong>{item.title}</strong><small>目标：{String(item.target_snapshot.knowledge_point ?? "未标注")} · 版本 {item.version} · 已派发 {runCounts[item.id] ?? 0} 人</small></div>{item.status === "draft" ? <button className="secondary-button" onClick={() => void action(item, "schedule")}>排程</button> : item.status === "scheduled" ? <button className="secondary-button" onClick={() => void action(item, "start")}>开始</button> : item.status === "active" ? <><button className="secondary-button" onClick={() => void action(item, "complete")}>完成</button><form className="member-form" onSubmit={(event) => void dispatch(event, item)}><select name="user_id" required defaultValue=""><option value="" disabled>选择学生后派发</option>{students.map((student) => <option key={student.user_id} value={student.user_id}>{student.display_name}</option>)}</select><button className="secondary-button" disabled={!students.length}>派发</button></form></> : item.status === "completed" ? <button className="primary-button" onClick={() => void action(item, "evaluate")}>记录效果</button> : null}</article>) : <p className="empty-state">尚未创建教师干预活动。</p>}</section>;
}
