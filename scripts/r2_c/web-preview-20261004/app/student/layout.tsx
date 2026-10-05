import type { ReactNode } from "react";
import WorkspaceRoleGuard from "../../components/WorkspaceRoleGuard";

export default function StudentLayout({ children }: { children: ReactNode }) {
  return <WorkspaceRoleGuard workspace="student">{children}</WorkspaceRoleGuard>;
}
