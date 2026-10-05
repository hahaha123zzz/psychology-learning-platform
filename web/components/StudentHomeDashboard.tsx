"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@iconify/react";
import { ApiError, api } from "../lib/api";

type Course = { id: string; title: string; term: string };
type TaskSummary = { task_id: string; course_id: string; status: string; state: string; updated_at: string };
type DueReview = { id: string; course_id: string; reason: string; due_at: string };
type Learning = { id: string; task_id: string; course_id: string; state: string; status: string; message?: string; tutor_message?: string };
type HomeProjection = {
  current_task: Learning | null;
  task_queue: TaskSummary[];
  due_reviews: DueReview[];
  next_actions: string[];
  progress_decision: { decision: string; reason: string; due_review_count: number };
  recent_activity: TaskSummary[];
};

const stateLabels: Record<string, string> = {
  diagnose: "诊断",
  teach: "学习",
  check: "理解检查",
  hint: "提示",
  practice: "练习",
  summary: "总结",
  completed: "已完成",
};

function errorText(reason: unknown) {
  return reason instanceof ApiError ? reason.message : "暂时无法读取学习安排，请检查服务后重试。";
}

export default function StudentHomeDashboard() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [projection, setProjection] = useState<HomeProjection | null>(null);
  const [notice, setNotice] = useState("正在整理你的学习安排…");

  useEffect(() => {
    Promise.all([api<Course[]>("/courses"), api<HomeProjection>("/student/home")])
      .then(([courseItems, home]) => {
        setCourses(courseItems);
        setProjection(home);
        setNotice("");
      })
      .catch((reason) => setNotice(errorText(reason)));
  }, []);

  function resume(taskId: string) {
    window.sessionStorage.setItem("student-learning-task", taskId);
  }

  const current = projection?.current_task ?? null;
  const currentCourse = courses.find((course) => course.id === current?.course_id);
  const otherTasks = projection?.task_queue.filter((task) => task.task_id !== current?.id) ?? [];

  return (
    <main className="course-list-page">
      <header className="course-list-header">
        <Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link>
        <span>学生学习首页</span>
      </header>
      <section className="course-list-content student-home-content">
        <div className="page-heading">
          <div><h1>继续你的学习</h1><p>当前任务和到期复习来自已授权课程的服务端状态。</p></div>
          <Link className="primary-button" href="/student/learning"><Icon icon="solar:play-circle-linear" />开始引导学习</Link>
        </div>
        {notice && <p className="status-banner" role="status">{notice}</p>}
        {projection && <>
          <section className="student-home-focus">
            <div className="student-home-focus-copy">
              <span className="eyebrow">下一步建议 · {projection.progress_decision.decision}</span>
              <h2>{projection.progress_decision.reason}</h2>
              {current ? <p>{currentCourse?.title ?? "当前课程"} · {stateLabels[current.state] ?? "学习任务"} · {current.status === "paused" ? "已暂停" : "进行中"}</p> : <p>目前没有进行中的学习任务，可以从已发布教材开始一个新任务。</p>}
            </div>
            {current && <Link className="primary-button" href="/student/learning" onClick={() => resume(current.id)}>
              <Icon icon={current.status === "paused" ? "solar:play-circle-linear" : "solar:arrow-right-circle-linear"} />
              {current.status === "paused" ? "恢复任务" : "继续任务"}
            </Link>}
          </section>

          <div className="student-home-grid">
            <section className="support-panel">
              <div className="panel-heading"><h2>待处理复习</h2><span>{projection.due_reviews.length} 项到期</span></div>
              {projection.due_reviews.length ? projection.due_reviews.slice(0, 5).map((review) => {
                const course = courses.find((item) => item.id === review.course_id);
                return <Link className="student-home-row" key={review.id} href={`/student/courses/${review.course_id}/practice`}>
                  <span><strong>{review.reason === "wrong_answer" ? "错题复习" : "间隔复习"}</strong><small>{course?.title ?? "课程"} · 到期 {new Date(review.due_at).toLocaleDateString("zh-CN")}</small></span>
                  <Icon icon="solar:arrow-right-linear" />
                </Link>;
              }) : <p className="empty-state student-home-empty">没有到期复习任务。</p>}
            </section>
            <section className="support-panel">
              <div className="panel-heading"><h2>可学习课程</h2><span>{courses.length} 门</span></div>
              {courses.length ? courses.slice(0, 6).map((course) => <article className="student-home-row" key={course.id}>
                <Link href={`/student/courses/${course.id}`}>
                  <span><strong>{course.title}</strong><small>{course.term} · 查看教材、练习与成长记录</small></span>
                </Link>
                <Link className="secondary-button" href={`/student/cases?course_id=${encodeURIComponent(course.id)}`}>案例推理</Link>
              </article>) : <p className="empty-state student-home-empty">当前账号还没有已授权课程。</p>}
            </section>
          </div>

          {otherTasks.length > 0 && <section className="support-panel student-home-queue">
            <div className="panel-heading"><h2>其他可恢复任务</h2><span>{otherTasks.length} 项</span></div>
            {otherTasks.slice(0, 5).map((task) => {
              const course = courses.find((item) => item.id === task.course_id);
              return <Link className="student-home-row" key={task.task_id} href="/student/learning" onClick={() => resume(task.task_id)}>
                <span><strong>{course?.title ?? "课程学习"} · {stateLabels[task.state] ?? "学习任务"}</strong><small>{task.status === "paused" ? "已暂停，可恢复" : "进行中"} · 最近更新 {new Date(task.updated_at).toLocaleDateString("zh-CN")}</small></span>
                <Icon icon="solar:arrow-right-linear" />
              </Link>;
            })}
          </section>}
        </>}
      </section>
    </main>
  );
}
