import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("workspaces are guarded by the account's effective role", () => {
  const guard = read("../components/WorkspaceRoleGuard.tsx");
  const teacherLayout = read("../app/teacher/layout.tsx");
  const studentLayout = read("../app/student/layout.tsx");
  const adminLayout = read("../app/admin/layout.tsx");

  assert.match(guard, /workspaceForRoles/);
  assert.match(teacherLayout, /workspace="teacher"/);
  assert.match(studentLayout, /workspace="student"/);
  assert.match(adminLayout, /workspace="admin"/);
});

test("retired teacher materials page stays informational and navigation is role scoped", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  const student = read("../components/StudentWorkspace.tsx");
  const navigation = read("../components/V2Navigation.tsx");

  assert.match(teacher, /role="status"/);
  assert.match(teacher, /联系课程内容管理员/);
  assert.doesNotMatch(teacher, /formatIssueDetail|uploadMaterialResumable/);
  assert.doesNotMatch(teacher, /href="\/student"/);
  assert.doesNotMatch(student, /href="\/teacher"/);
  assert.match(navigation, /workspaceForRoles/);
});
