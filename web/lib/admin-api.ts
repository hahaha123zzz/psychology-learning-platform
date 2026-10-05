import { api, ApiError, idempotencyKey } from "./api";

export type AdminPage<T> = { items: T[]; nextCursor: string | null; hasMore: boolean };

async function adminPage<T>(path: string): Promise<AdminPage<T>> {
  const response = await fetch(`/api/v1${path}`, { credentials: "include" });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(
    response.status,
    body?.error?.message ?? "请求失败，请稍后重试",
    body?.error?.details,
    body?.error?.code,
    Boolean(body?.error?.retryable),
  );
  return {
    items: Array.isArray(body?.data) ? body.data as T[] : [],
    nextCursor: typeof body?.meta?.next_cursor === "string" ? body.meta.next_cursor : null,
    hasMore: Boolean(body?.meta?.has_more),
  };
}

export type RoleAssignmentTarget = { id: string; email: string; display_name: string };
export type CourseScopeOption = { id: string; title: string; term: string };
export type AdminCourse = { id: string; title: string; term: string; status: string; version: number; created_at: string };
export type AdminGovernedClass = {
  id: string; course_id: string; code: string; name: string; status: string; version: number;
  member_count: number; active_teacher_count: number; created_at: string; updated_at: string;
};
export type AdminCourseMember = {
  id: string; user_id: string; display_name: string; role: "student" | "teacher" | "assistant";
  status: string; version: number; created_at: string; updated_at: string;
};
export type AdminClassMember = {
  id: string; user_id: string; display_name: string; status: string; version: number; created_at: string; updated_at: string;
};
export type AdminClassAssignment = {
  id: string;
  class_id: string;
  class_code: string;
  class_name: string;
  teacher_id: string;
  teacher_name: string;
  assignment_role: "lead" | "assistant";
  status: "active" | "ended";
  version: number;
  assigned_by: string;
  created_at: string;
};
export type AdminClassAssignmentOptions = {
  course_id: string;
  classes: { id: string; code: string; name: string }[];
  teachers: { id: string; display_name: string; course_role: "teacher" | "assistant" }[];
  assignments: AdminClassAssignment[];
};
export type AdminJob = {
  id: string;
  kind: "material_parse" | "material_embed";
  status: "queued" | "running" | "failed" | "succeeded" | "cancelled";
  stage: string | null;
  progress: number;
  retryable: boolean;
  attempt_count: number;
  version: number;
  course_id: string;
  has_error: boolean;
  created_at: string;
  updated_at: string;
};

export type AdminAuditLog = {
  id: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  course_id: string | null;
  created_at: string;
};

export function listAdminCourses(page: { limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ limit: String(page.limit ?? 50) });
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<AdminCourse>(`/admin/courses?${params.toString()}`);
}

export function listAdminClasses(courseId: string, page: { limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ limit: String(page.limit ?? 50) });
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<AdminGovernedClass>(`/admin/courses/${encodeURIComponent(courseId)}/classes?${params.toString()}`);
}

export function listAdminCourseMembers(courseId: string, status: "active" | "removed" | "all" = "active", page: { limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ status, limit: String(page.limit ?? 50) });
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<AdminCourseMember>(`/admin/courses/${encodeURIComponent(courseId)}/members?${params.toString()}`);
}

export function listAdminClassMembers(classId: string, status: "active" | "removed" | "all" = "active", page: { limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ status, limit: String(page.limit ?? 50) });
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<AdminClassMember>(`/admin/classes/${encodeURIComponent(classId)}/members?${params.toString()}`);
}

export function createAdminClass(courseId: string, input: { code: string; name: string; reason: string }, requestKey?: string) {
  return api<AdminGovernedClass>(`/admin/courses/${encodeURIComponent(courseId)}/classes`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
    body: JSON.stringify(input),
  });
}

export function addAdminCourseMember(courseId: string, input: { user_id: string; role: AdminCourseMember["role"]; reason: string }, requestKey?: string) {
  return api<AdminCourseMember>(`/admin/courses/${encodeURIComponent(courseId)}/members`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
    body: JSON.stringify(input),
  });
}

export function addAdminClassMember(classId: string, input: { user_id: string; reason: string }, requestKey?: string) {
  return api<AdminClassMember>(`/admin/classes/${encodeURIComponent(classId)}/members`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
    body: JSON.stringify(input),
  });
}

export function removeAdminCourseMember(courseId: string, memberId: string, version: number, reason: string, requestKey?: string) {
  return api<{ id: string; status: "removed"; version: number }>(
    `/admin/courses/${encodeURIComponent(courseId)}/members/${encodeURIComponent(memberId)}/remove`,
    { method: "POST", headers: { "Idempotency-Key": requestKey ?? idempotencyKey() }, body: JSON.stringify({ version, reason }) },
  );
}

export function removeAdminClassMember(classId: string, memberId: string, version: number, reason: string, requestKey?: string) {
  return api<{ id: string; status: "removed"; version: number }>(
    `/admin/classes/${encodeURIComponent(classId)}/members/${encodeURIComponent(memberId)}/remove`,
    { method: "POST", headers: { "Idempotency-Key": requestKey ?? idempotencyKey() }, body: JSON.stringify({ version, reason }) },
  );
}

export function listAdminAuditLogs(input: { course_id?: string; action?: string; limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ limit: String(input.limit ?? 50) });
  if (input.course_id?.trim()) params.set("course_id", input.course_id.trim());
  if (input.action?.trim()) params.set("action", input.action.trim());
  if (input.cursor) params.set("cursor", input.cursor);
  return adminPage<AdminAuditLog>(`/admin/audit-logs?${params.toString()}`);
}

export type RoleAssignment = {
  id: string;
  user_id: string;
  user_email: string;
  user_display_name: string;
  role: string;
  scope_type: "platform" | "course" | "class";
  scope_id: string | null;
  status: "active" | "revoked";
  version: number;
  granted_by: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminOperationKeyCache = Map<string, { fingerprint: string; key: string }>;

export function adminOperationKey(cache: AdminOperationKeyCache, operation: string, payload: unknown) {
  const fingerprint = JSON.stringify(payload) ?? String(payload);
  const pending = cache.get(operation);
  if (pending?.fingerprint === fingerprint) return pending.key;
  const key = idempotencyKey();
  cache.set(operation, { fingerprint, key });
  return key;
}

export function clearAdminOperationKey(cache: AdminOperationKeyCache, operation: string) {
  cache.delete(operation);
}

export function listRoleAssignments(
  status: "active" | "revoked" | "all" = "active",
  scopeType?: RoleAssignment["scope_type"],
  scopeId?: string,
  page: { limit?: number; cursor?: string } = {},
) {
  const params = new URLSearchParams({ status, limit: String(page.limit ?? 50) });
  if (scopeType) params.set("scope_type", scopeType);
  if (scopeId) params.set("scope_id", scopeId);
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<RoleAssignment>(`/admin/role-assignments?${params.toString()}`);
}

export function searchRoleAssignmentTargets(query: string) {
  return api<RoleAssignmentTarget[]>(`/admin/role-assignment-targets?q=${encodeURIComponent(query)}`);
}

export function listRoleAssignmentCourses() {
  return api<CourseScopeOption[]>("/admin/role-assignment-courses");
}

export function grantRoleAssignment(input: {
  user_id: string;
  role: string;
  scope_type: "platform" | "course";
  scope_id: string | null;
  reason: string;
}, requestKey?: string) {
  return api<RoleAssignment>("/admin/role-assignments", {
    method: "POST",
    headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
    body: JSON.stringify(input),
  });
}

export function revokeRoleAssignment(id: string, version: number, reason: string, requestKey?: string) {
  return api<RoleAssignment>(`/admin/role-assignments/${id}/revoke`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
    body: JSON.stringify({ version, reason }),
  });
}

export function listAdminJobs(status: AdminJob["status"] | "all" = "all", page: { limit?: number; cursor?: string } = {}) {
  const params = new URLSearchParams({ limit: String(page.limit ?? 50) });
  if (page.cursor) params.set("cursor", page.cursor);
  return adminPage<AdminJob>(`/admin/jobs?status=${encodeURIComponent(status)}&${params.toString()}`);
}

export function retryAdminJob(id: string, version: number, reason: string, requestKey?: string) {
  return api<Pick<AdminJob, "id" | "kind" | "status" | "stage" | "retryable" | "attempt_count" | "version">>(
    `/admin/jobs/${id}/retry`,
    {
      method: "POST",
      headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
      body: JSON.stringify({ version, reason }),
    },
  );
}

export function getAdminClassAssignmentOptions(courseId: string) {
  return api<AdminClassAssignmentOptions>(
    `/admin/class-assignment-options?course_id=${encodeURIComponent(courseId)}`,
  );
}

export function assignAdminClassTeacher(input: {
  class_id: string;
  teacher_id: string;
  assignment_role: "lead" | "assistant";
  reason: string;
}, requestKey?: string) {
  return api<Pick<AdminClassAssignment, "id" | "class_id" | "teacher_id" | "assignment_role" | "status" | "version"> & { teacher_name: string; assigned_by: string; created_at: string }>(
    "/admin/class-teacher-assignments",
    {
      method: "POST",
      headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
      body: JSON.stringify(input),
    },
  );
}

export function endAdminClassTeacherAssignment(id: string, version: number, reason: string, requestKey?: string) {
  return api<Pick<AdminClassAssignment, "id" | "class_id" | "teacher_id" | "assignment_role" | "status" | "version"> & { teacher_name: string; assigned_by: string; created_at: string }>(
    `/admin/class-teacher-assignments/${id}/end`,
    {
      method: "POST",
      headers: { "Idempotency-Key": requestKey ?? idempotencyKey() },
      body: JSON.stringify({ version, reason }),
    },
  );
}
