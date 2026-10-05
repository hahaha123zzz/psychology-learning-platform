import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/student/branches/page.tsx", import.meta.url), "utf8");
const component = readFileSync(new URL("../components/StudentBranches.tsx", import.meta.url), "utf8");

test("学生局部分支路由加载真实分支工作台而非案例工作台", () => {
  assert.match(page, /import StudentBranches from/);
  assert.match(page, /return <StudentBranches \/>/);
  assert.doesNotMatch(page, /StudentCaseWorkbench/);
});

test("分支来源必须选择本人发言并由服务端核对原文片段", () => {
  assert.match(component, /turn\.role === "student"/);
  assert.match(component, /source\.content\.includes\(normalizedSelection\)/);
  assert.match(component, /source_turn_id: source\.id/);
});

test("分支合并显式确认并保留幂等键用于同请求重试", () => {
  assert.match(component, /merge_key: requestKey/);
  assert.match(component, /confirmed: true/);
  assert.match(component, /const requestKey = mergeKey \|\| idempotencyKey\(\)/);
  assert.match(component, /重试沿用同一 key/);
  assert.doesNotMatch(component, /prompt\(/);
});
