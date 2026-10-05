import type { ReactNode } from "react";
import WorkspaceRoleGuard from "../../components/WorkspaceRoleGuard";

export default function TeacherLayout({ children }: { children: ReactNode }) {
  return <WorkspaceRoleGuard workspace="teacher">{children}</WorkspaceRoleGuard>;
}
