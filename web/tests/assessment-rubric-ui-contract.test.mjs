import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/TeacherAssessments.tsx", import.meta.url),
  "utf8",
);

test("Rubric authoring binds criteria and evidence to the selected question version", () => {
  assert.match(source, /question_version_id: versionId/);
  assert.match(source, /evidence_refs: \[draft\.evidenceRef\]/);
  assert.match(source, /max_score: criteria\.reduce\(\(sum, item\) => sum \+ item\.points, 0\)/);
  assert.match(source, /anchors: \{ "0": item\.zeroAnchor\.trim\(\), \[item\.points\]: item\.fullAnchor\.trim\(\) \}/);
  assert.match(source, /version\.evidence_ids\.map/);
});

test("formal purpose and Rubric review require explicit rationale and use review APIs", () => {
  assert.match(source, /purposeReasons\[question\.id\]/);
  assert.match(source, /reason\.length < 8/);
  assert.match(source, /purpose\/formal/);
  assert.match(source, /rubrics\/\$\{rubric\.id\}\/approve/);
  assert.match(source, /rubricApprovalReasons\[rubric\.id\]/);
  assert.doesNotMatch(source, /经课程教师复核，批准用于正式测评/);
});

test("teacher grading stays manual and AI grading suggestions stay disabled", () => {
  assert.match(source, /Rubric 仅为教师人工评分提供版本化依据/);
  assert.match(source, /不会自动评分或生成 AI 评分建议/);
  assert.doesNotMatch(source, /grading-suggestions|ai-grading-suggestions/i);
});
