"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";

export type Workspace = "student" | "teacher" | "courseDesigner" | "admin";
type Me = { platform_roles: string[] };

export function workspaceForRoles(roles: string[]): Workspace {
  if (roles.includes("admin")) return "admin";
  if (roles.includes("course_publisher") || roles.includes("course_designer")) return "courseDesigner";
  if (roles.includes("teacher")) return "teacher";
  return "student";
}

export default function WorkspaceRoleGuard({
  workspace,
  children,
}: {
  workspace: Workspace;
  children: ReactNode;
}) {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    let active = true;
    api<Me>("/me")
      .then((me) => {
        const effectiveWorkspace = workspaceForRoles(me.platform_roles);
        if (!active) return;
        if (effectiveWorkspace === workspace) {
          setAllowed(true);
          return;
        }
        router.replace(`/${effectiveWorkspace}`);
      })
      .catch(() => router.replace(`/login?next=/${workspace}`));
    return () => {
      active = false;
    };
  }, [router, workspace]);

  if (!allowed) {
    return <main className="functional-app"><p className="empty-state">正在验证访问权限…</p></main>;
  }
  return <>{children}</>;
}
