"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { Icon } from "@iconify/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";

export type Course = { id: string; title: string; term: string; description?: string | null };
export type CourseRole = "teacher" | "student";

type NavItem = { label: string; icon: string; suffix: string };
const NAVIGATION: Record<CourseRole, NavItem[]> = {
  teacher: [
    { label: "课程概览", icon: "solar:widget-2-linear", suffix: "" },
    { label: "教材", icon: "solar:book-bookmark-linear", suffix: "/materials" },
  ],
  student: [
    { label: "首页", icon: "solar:home-2-linear", suffix: "" },
    { label: "学习", icon: "solar:book-2-linear", suffix: "/learn" },
    { label: "练习", icon: "solar:pen-new-square-linear", suffix: "/practice" },
    { label: "成长", icon: "solar:chart-square-linear", suffix: "/growth" },
    { label: "我的", icon: "solar:user-rounded-linear", suffix: "/me" },
  ],
};

function errorText(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "暂时无法读取课程信息，请检查服务后重试。";
}
export default function CourseShell({ role, children }: { role: CourseRole; children: ReactNode }) {
  const params = useParams<{ courseId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [notice, setNotice] = useState("");
  const courseId = params.courseId;

  useEffect(() => {
    let alive = true;
    api<Course[]>("/courses")
      .then((items) => {
        if (!alive) return;
        setCourses(items);
        if (items.length && !items.some((course) => course.id === courseId)) router.replace(`/${role}/courses`);
      })
      .catch((reason) => alive && setNotice(errorText(reason)));
    return () => { alive = false; };
  }, [courseId, role, router]);

  const current = useMemo(() => courses.find((course) => course.id === courseId), [courses, courseId]);
  const base = `/${role}/courses/${courseId}`;
  const nav = NAVIGATION[role];

  return <main className={`course-app ${role}-course-app`}>
    <header className="course-header">
      <Link href={`/${role}/courses`} className="back-to-courses"><Icon icon="solar:arrow-left-linear" />{role === "teacher" ? "我的课程" : "我的学习"}</Link>
      <span className="header-divider" />
      <div className="course-identity"><strong>{current?.title ?? "正在读取课程…"}</strong><small>{current?.term ?? ""}</small></div>
      <span className="header-spacer" />
      {role === "teacher" && <Link className="task-trigger" href={`${base}/materials#tasks`}><Icon icon="solar:bell-bing-linear" />处理进度</Link>}
      <Link className="profile-button" href={role === "student" ? `${base}/me` : "/"}><span className="avatar">我</span><span>账号</span></Link>
    </header>
    {notice && <div className="shell-notice" role="alert">{notice}</div>}
    <div className="course-layout">
      <nav className="course-navigation" aria-label={role === "teacher" ? "教师课程导航" : "学生课程导航"}>
        {nav.map((item) => {
          const href = `${base}${item.suffix}`;
          const active = item.suffix ? pathname === href || pathname.startsWith(`${href}/`) : pathname === base;
          return <Link className={active ? "course-nav-item active" : "course-nav-item"} href={href} key={item.label}><Icon icon={item.icon} /><span>{item.label}</span></Link>;
        })}
      </nav>
      <section className="course-content">{children}</section>
    </div>
  </main>;
}
