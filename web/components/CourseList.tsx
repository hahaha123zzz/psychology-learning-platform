"use client";

import Link from "next/link";
import { Icon } from "@iconify/react";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, idempotencyKey } from "../lib/api";
import type { Course, CourseRole } from "./CourseShell";

function errorText(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "暂时无法读取课程，请检查服务后重试。";
}
export default function CourseList({ role }: { role: CourseRole }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [notice, setNotice] = useState("正在读取课程…");
  const [creating, setCreating] = useState(false);

  const load = () => api<Course[]>("/courses").then((items) => { setCourses(items); setNotice(""); }).catch((reason) => setNotice(errorText(reason)));
  useEffect(() => { void load(); }, []);

  async function createCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const course = await api<Course>("/courses", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({ title: data.get("title"), term: data.get("term"), description: data.get("description") || null, timezone: "Asia/Shanghai" }),
      });
      setCourses((items) => [course, ...items]);
      setCreating(false);
      setNotice("课程已创建。");
    } catch (reason) { setNotice(errorText(reason)); }
  }

  const base = `/${role}/courses`;
  return <main className="course-list-page">
    <header className="course-list-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><span>{role === "teacher" ? "教师课程" : "学生学习"}</span></header>
    <section className="course-list-content">
      <div className="page-heading"><div><h1>{role === "teacher" ? "我的课程" : "我的学习"}</h1><p>{role === "teacher" ? "选择一门课程，管理教材、练习和班级学习情况。" : "选择一门课程，继续阅读、练习和复习。"}</p></div>{role === "teacher" && <button className="primary-button" onClick={() => setCreating((value) => !value)}><Icon icon="solar:add-circle-linear" />新建课程</button>}</div>
      {notice && <p className="status-banner">{notice}</p>}
      {creating && <form className="course-create-form" onSubmit={createCourse}><input name="title" required placeholder="课程名称" /><input name="term" required placeholder="学期，例如 2026 秋" /><input name="description" placeholder="课程说明（可选）" /><button className="primary-button">创建课程</button><button type="button" onClick={() => setCreating(false)}>取消</button></form>}
      <div className="course-card-grid">
        {courses.map((course) => <Link href={`${base}/${course.id}`} className="course-card" key={course.id}><Icon icon={role === "teacher" ? "solar:clipboard-check-bold-duotone" : "solar:book-bookmark-bold-duotone"} /><div><strong>{course.title}</strong><span>{course.term}</span><small>{course.description || (role === "teacher" ? "进入课程工作台" : "进入学习空间")}</small></div><Icon className="course-card-arrow" icon="solar:arrow-right-linear" /></Link>)}
      </div>
      {!notice && courses.length === 0 && <section className="course-empty"><Icon icon="solar:book-linear" /><h2>{role === "teacher" ? "还没有课程" : "暂时没有可学习的课程"}</h2><p>{role === "teacher" ? "新建课程后即可上传教材并组织教学。" : "请联系教师确认你已加入课程，且课程已有发布的教材。"}</p></section>}
    </section>
  </main>;
}
