export const workspaceRoutes = {
  student: "/student",
  teacher: "/teacher",
  courseDesigner: "/course-design",
  admin: "/admin",
} as const;

export type WorkspaceRole = keyof typeof workspaceRoutes;

export function routeForRole(role: WorkspaceRole): string {
  return workspaceRoutes[role];
}

