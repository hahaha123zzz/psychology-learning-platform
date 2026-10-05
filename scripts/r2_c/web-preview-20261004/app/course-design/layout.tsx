import type { ReactNode } from "react";
import WorkspaceRoleGuard from "../../components/WorkspaceRoleGuard";

export default function CourseDesignLayout({ children }: { children: ReactNode }) {
  return <WorkspaceRoleGuard workspace="courseDesigner">{children}</WorkspaceRoleGuard>;
}
