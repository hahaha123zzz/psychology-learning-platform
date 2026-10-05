"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../lib/api";
import {
  listStudentInterventionRuns,
  transitionStudentInterventionRun,
  type InterventionRun,
} from "../lib/interventions-api";

const explain = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "活动执行状态暂时无法更新。";

export default function StudentInterventionRunsPanel({ courseId }: { courseId: string }) {
  const [runs, setRuns] = useState<InterventionRun[]>([]);
  const [notice, setNotice] = useState("正在读取教师安排…");
  const load = useCallback(() => listStudentInterventionRuns(courseId).then(setRuns).then(() => setNotice("")).catch((reason) => setNotice(explain(reason))), [courseId]);
  useEffect(() => { void load(); }, [load]);

  async function transition(run: InterventionRun, action: "start" | "complete") {
    try {
      const next = await transitionStudentInterventionRun(
        run,
        action,
        action === "complete" ? { reflection: "学生已确认完成本次活动" } : undefined,
      );
      setRuns((current) => current.map((candidate) => candidate.id === next.id ? next : candidate));
      setNotice(action === "complete" ? "活动已完成；完成本身不会直接改变掌握状态。" : "活动已开始。 ");
    } catch (reason) {
      setNotice(explain(reason));
    }
  }

  return <section className="support-panel teacher-list"><div className="panel-heading"><h2>教师安排</h2><span>{runs.length} 项</span></div>{notice && <p className="status-banner">{notice}</p>}{runs.length ? runs.map((run) => <article className="teacher-row" key={run.id}><div><span className={`status-tag ${run.status}`}>{run.status}</span><small>执行版本 {run.version}</small></div>{run.status === "scheduled" ? <button className="secondary-button" onClick={() => void transition(run, "start")}>开始活动</button> : run.status === "in_progress" ? <button className="primary-button" onClick={() => void transition(run, "complete")}>完成活动</button> : null}</article>) : <p className="empty-state">当前没有待执行的教师安排。</p>}</section>;
}
