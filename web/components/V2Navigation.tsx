"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  ["教师资料", "/teacher"], ["题库", "/teacher/questions"], ["测验配置", "/teacher/assessments"], ["成员", "/teacher/members"],
  ["学生学习", "/student"], ["引导学习", "/student/learning"], ["学生测验", "/student/assessments"], ["局部追问", "/student/branches"], ["记忆与隐私", "/student/profile"], ["管理", "/admin"],
] as const;

export default function V2Navigation() {
  const path = usePathname();
  if (path === "/" || path === "/login") return null;
  return <nav className="v2-navigation" aria-label="V2 功能导航">{items.map(([label, href]) => <Link className={path === href ? "active" : ""} href={href} key={href}>{label}</Link>)}</nav>;
}
