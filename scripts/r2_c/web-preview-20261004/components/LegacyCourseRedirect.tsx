"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import type { Course, CourseRole } from "./CourseShell";

export default function LegacyCourseRedirect({ role, suffix = "" }: { role: CourseRole; suffix?: string }) {
  const router = useRouter();
  useEffect(() => {
    let alive = true;
    api<Course[]>("/courses").then((courses) => {
      if (!alive) return;
      router.replace(courses[0] ? `/${role}/courses/${courses[0].id}${suffix}` : `/${role}/courses`);
    }).catch(() => alive && router.replace(`/${role}/courses`));
    return () => { alive = false; };
  }, [role, router, suffix]);
  return <main className="route-loading" aria-live="polite">正在进入课程…</main>;
}
