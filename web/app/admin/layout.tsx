import type { ReactNode } from "react";
import WorkspaceRoleGuard from "../../components/WorkspaceRoleGuard";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <WorkspaceRoleGuard workspace="admin">{children}</WorkspaceRoleGuard>;
}
