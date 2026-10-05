import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("Admin route mounts one five-section accessible governance workspace", () => {
  const route = read("../app/admin/page.tsx");
  const workspace = read("../components/AdminWorkspace.tsx");

  assert.match(route, /return\s*<AdminWorkspace\s*\/>/);
  assert.doesNotMatch(route, /<Admin(?:Jobs|ClassAssignments|RoleAssignments)Panel/);
  for (const id of ["overview", "iam", "classes", "jobs", "audit"]) {
    assert.match(workspace, new RegExp(`id: "${id}"`));
    assert.match(workspace, new RegExp(`admin-panel-${id}`));
  }
  assert.match(workspace, /role="tablist"/);
  assert.match(workspace, /role="tab"/);
  assert.match(workspace, /role="tabpanel"/);
});

test("Admin overview reads service health without projecting learning or private content", () => {
  const overview = read("../components/AdminOverviewPanel.tsx");
  const service = read("../lib/admin-governance.ts");
  assert.match(overview, /loadAdminGovernanceOverview\(\)/);
  assert.match(overview, /role="alert"/);
  assert.match(overview, /重试/);
  assert.match(service, /\/api\/v1\/health\/ready/);
  assert.match(service, /api<unknown>\("\/admin\/health"/);
  assert.match(service, /organizationUserCount: finiteCount\(counts\?\.users\)/);
  assert.match(service, /inProgressAttempts: finiteCount\(admin\.attempts_in_progress\)/);
  assert.doesNotMatch(service, /memory_items|learning_evidences|model_call_logs|model_calls/);
  assert.doesNotMatch(overview, /student|学生作答|私聊正文|memory_content/i);
});

test("IAM controls use scoped live APIs and replay-stable mutation keys", () => {
  const panel = read("../components/AdminRoleAssignmentsPanel.tsx");
  const client = read("../lib/admin-api.ts");

  assert.match(panel, /listRoleAssignments\(/);
  assert.match(panel, /scopeFilter/);
  assert.match(panel, /adminOperationKey\(/);
  assert.match(panel, /clearAdminOperationKey\(/);
  assert.match(panel, /await load\(\)/);
  assert.match(panel, /授权理由/);
  assert.match(panel, /撤销理由/);
  assert.match(panel, /AdminConfirmationDialog/);
  assert.match(panel, /useAdminWriteGate/);
  assert.match(panel, /error\.status === 409/);
  assert.match(panel, /role=\{noticeIsError \? "alert" : "status"\}/);
  assert.match(panel, /load\(nextCursor, true\)/);
  assert.match(panel, /已加载 \{items\.length\} 条/);
  assert.match(client, /\/admin\/role-assignments/);
  assert.match(client, /Idempotency-Key/);
  assert.match(client, /meta\?\.next_cursor/);
  assert.match(client, /meta\?\.has_more/);
});

test("Course and class governance stays within assignment options and refreshes after conflicts", () => {
  const panel = read("../components/AdminClassAssignmentsPanel.tsx");
  const client = read("../lib/admin-api.ts");

  assert.match(panel, /getAdminClassAssignmentOptions/);
  assert.match(panel, /adminOperationKey\(/);
  assert.match(panel, /clearAdminOperationKey\(/);
  assert.match(panel, /await loadOptions\(courseId\)/);
  assert.match(panel, /任课对象必须已是该课程的教师或助教成员/);
  assert.match(panel, /分配理由/);
  assert.match(panel, /结束理由/);
  assert.match(panel, /AdminConfirmationDialog/);
  assert.match(panel, /useAdminWriteGate/);
  assert.match(panel, /课程成员与班级学生成员由上方独立管理员入口维护/);
  assert.match(client, /\/admin\/class-assignment-options/);
  assert.match(client, /\/admin\/class-teacher-assignments/);
});

test("Job recovery uses minimal live status, versioned reasons, and stable retry keys", () => {
  const panel = read("../components/AdminJobsPanel.tsx");
  const client = read("../lib/admin-api.ts");

  assert.match(panel, /listAdminJobs\(status, \{ limit, cursor \}\)/);
  assert.match(panel, /retryAdminJob\(/);
  assert.match(panel, /adminOperationKey\(/);
  assert.match(panel, /clearAdminOperationKey\(/);
  assert.match(panel, /await load\(\)/);
  assert.match(panel, /原始错误详情不在管理员面板展示/);
  assert.match(panel, /最多 5 次尝试上限/);
  assert.match(panel, /AdminConfirmationDialog/);
  assert.match(panel, /useAdminWriteGate/);
  assert.match(panel, /load\(nextCursor, true\)/);
  assert.match(client, /\/admin\/jobs\?status=\$\{encodeURIComponent\(status\)\}/);
  assert.match(client, /\/admin\/jobs\/\$\{id\}\/retry/);
});

test("Audit view applies exact server filters, cursor pagination, and ignores stale responses", () => {
  const panel = read("../components/AdminAuditPanel.tsx");
  const client = read("../lib/admin-api.ts");

  assert.match(panel, /course_id: courseInput\.trim\(\) \|\| undefined/);
  assert.match(panel, /action: actionInput\.trim\(\) \|\| undefined/);
  assert.match(panel, /requestVersion/);
  assert.match(panel, /currentRequest !== requestVersion\.current/);
  assert.match(panel, /fetchLogs\(nextCursor, true\)/);
  assert.match(panel, /hasMore/);
  assert.match(panel, /每页/);
  assert.match(client, /listAdminAuditLogs/);
  assert.match(client, /course_id/);
  assert.match(client, /action/);
});

test("Course governance exposes scoped, paged metadata and confirmation-gated membership mutations", () => {
  const panel = read("../components/AdminCourseGovernancePanel.tsx");
  const client = read("../lib/admin-api.ts");

  for (const endpoint of [
    "/admin/courses?", "/admin/courses/${encodeURIComponent(courseId)}/classes?",
    "/admin/courses/${encodeURIComponent(courseId)}/members?", "/admin/classes/${encodeURIComponent(classId)}/members?",
    "/members/${encodeURIComponent(memberId)}/remove",
  ]) assert.ok(client.includes(endpoint), `missing API path: ${endpoint}`);
  assert.match(panel, /AdminConfirmationDialog/);
  assert.match(panel, /useAdminWriteGate/);
  assert.match(panel, /搜索仅提供同机构候选账号/);
  assert.match(panel, /服务端会再次校验/);
  assert.match(panel, /current version|version v|当前版本/);
  assert.match(panel, /adminOperationKey\(/);
  assert.match(panel, /error\.status === 409/);
  assert.match(panel, /软移除/);
  assert.match(panel, /loadCourseMembers\(action\.courseId\)/);
  assert.match(panel, /loadClassMembers\(action\.classId\)/);
});

test("Admin mutations are server-confirmed and narrow viewport fails closed", () => {
  const gate = read("../app/admin/useAdminWriteGate.ts");
  const dialog = read("../components/AdminConfirmationDialog.tsx");
  const api = read("../lib/admin-api.ts");

  assert.match(gate, /min-width: 721px/);
  assert.match(gate, /viewportReady && wideEnough/);
  assert.match(dialog, /showModal\(\)/);
  assert.match(dialog, /aria-describedby/);
  assert.match(api, /limit: String\(page\.limit \?\? 50\)/);
  assert.match(api, /next_cursor/);
  assert.match(api, /has_more/);
  assert.match(api, /Idempotency-Key/);
});
