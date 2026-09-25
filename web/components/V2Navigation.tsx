"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api } from "../lib/api";
import { workspaceForRoles, type Workspace } from "./WorkspaceRoleGuard";

const items: Record<Workspace, readonly [string, string][]> = {
  teacher: [["教材资料", "/teacher"], ["题库", "/teacher/questions"], ["测验配置", "/teacher/assessments"], ["成员", "/teacher/members"]],
  student: [["教材学习", "/student"], ["引导学习", "/student/learning"], ["课程测验", "/student/assessments"], ["局部追问", "/student/branches"], ["记忆与隐私", "/student/profile"]],
  admin: [["管理", "/admin"]],
};

export default function V2Navigation() {
  const path = usePathname();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  useEffect(() => {
    api<{ platform_roles: string[] }>("/me")
      .then((me) => setWorkspace(workspaceForRoles(me.platform_roles)))
      .catch(() => setWorkspace(null));
  }, []);
  if (path === "/" || path === "/login") return null;
  if (!workspace) return null;
  return <nav className="v2-navigation" aria-label="工作区导航">{items[workspace].map(([label, href]) => <Link className={path === href ? "active" : ""} href={href} key={href}>{label}</Link>)}</nav>;
}
