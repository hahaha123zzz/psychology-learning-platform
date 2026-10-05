import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("growth view explains recorded evidence and does not re-label knowledge as skill", () => {
  const source = read("../components/StudentCourseSupportPages.tsx");
  assert.match(source, /当前服务端只有知识点掌握记录，没有独立技能证据/);
  assert.match(source, /待复核的学习记忆不作为误区结论展示/);
  assert.match(source, /依据 \{item\.evidence_count\} 条/);
  assert.match(source, /规则 \{item\.algorithm_version\}/);
  assert.match(source, /item\.state_reason/);
  assert.match(source, /role="tabpanel"/);
  assert.doesNotMatch(source, /tabs\?\.misconceptions\.map/);
});

test("personal memory view uses the actual service fields and exposes provenance and review timing", () => {
  const source = read("../components/StudentCourseSupportPages.tsx");
  assert.match(source, /type MemorySummary = \{ summary: Record<string, number>; stale_hidden: number \}/);
  assert.match(source, /item\.content/);
  assert.match(source, /item\.provenance_level/);
  assert.match(source, /item\.evidence_refs\.length/);
  assert.match(source, /item\.review_after/);
  assert.match(source, /summary\.stale_hidden/);
  assert.match(source, /<StudentPreferencesPanel \/>/);
  assert.match(source, /<StudentNotificationsPanel \/>/);
});

test("preference edits stay controlled and retryable when a save response is lost", () => {
  const source = read("../components/StudentPreferencesPanel.tsx");
  assert.match(source, /value=\{p\.hint_density\}/);
  assert.match(source, /checked=\{p\.reduced_motion\}/);
  assert.match(source, /当前选择仍保留，可重试保存/);
  assert.match(source, /role="status" aria-live="polite"/);
});

test("learning and SSE inputs remain accessible and recoverable after network failure", () => {
  const session = read("../components/StudentLearningSession.tsx");
  const learn = read("../components/StudentLearnPage.tsx");
  assert.match(session, /aria-label="回答当前学习问题"/);
  assert.match(session, /你的回答仍保留，可重试/);
  assert.match(session, /setRecoveryTaskId\(taskId\)/);
  assert.doesNotMatch(session, /catch \{\s*window\.sessionStorage\.removeItem\("student-learning-task"\);\s*\}/);
  assert.match(session, /恢复后会读取服务端已保存的进度/);
  assert.match(session, /重试恢复学习/);
  assert.match(session, /disabled=\{recovering\}/);
  assert.match(learn, /你的问题仍保留在输入框/);
  assert.match(learn, /aria-label="围绕教材提问"/);
  assert.match(learn, /aria-live="polite" aria-relevant="additions text"/);
  assert.match(learn, /eventData\.event === "state"/);
  assert.match(learn, /eventData\.event === "done"/);
  assert.match(learn, /回答已保存/);
  assert.match(learn, /EvidencePointerDrawer label="打开引用" pointerId=\{citation\.pointerId\}/);
});

test("case workbench has a dedicated student route separate from Branch", () => {
  const route = read("../app/student/cases/page.tsx");
  const home = read("../components/StudentHomeDashboard.tsx");
  assert.match(route, /StudentCaseWorkbench/);
  assert.match(home, /\/student\/cases\?course_id=/);
});

test("student home has one service-backed learning action plus retry and practice shortcuts", () => {
  const home = read("../components/StudentHomeDashboard.tsx");
  assert.match(home, /api<Course\[]>\("\/courses"\)/);
  assert.match(home, /api<HomeProjection>\("\/student\/home"\)/);
  assert.match(home, /current\?\.task_id \?\? current\?\.id/);
  assert.match(home, /恢复当前任务/);
  assert.match(home, /开始引导学习/);
  assert.match(home, /onClick=\{\(\) => void loadHome\(\)\}>重试/);
  assert.match(home, /aria-label="复习和练习入口"/);
  assert.match(home, /student-home-no-course/);
  assert.doesNotMatch(home, /fixture|mock/i);
});
