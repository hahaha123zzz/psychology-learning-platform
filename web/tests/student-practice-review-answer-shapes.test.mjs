import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../components/StudentCourseSupportPages.tsx", import.meta.url),
  "utf8",
);
const practice = source.slice(
  source.indexOf("export function StudentPracticePage()"),
  source.indexOf("export function StudentGrowthPage()"),
);

test("Review verification payload matches the Practice question response shape", () => {
  const helper = source.slice(
    source.indexOf("function reviewVerificationResponse"),
    source.indexOf("function ReviewAnswerControl"),
  );
  assert.match(helper, /question\.type === "true_false"[\s\S]*?typeof answer === "boolean" \? \{ selected_keys: answer \}/);
  assert.match(helper, /question\.type === "single"[\s\S]*?selected_keys: \[answer\]/);
  assert.match(helper, /question\.type === "multiple"[\s\S]*?selected_keys: \[\.\.\.new Set\(answer\)\]/);
  assert.match(helper, /answer\.every\(\(key\) => optionKeys\.has\(key\)\)/);
  assert.match(practice, /body: JSON\.stringify\(\{ version: reviewVersions\.current\[task\.id\] \?\? task\.version, response \}\)/);
});

test("Review offers accessible controls only for supported objective question types", () => {
  const controls = source.slice(
    source.indexOf("function ReviewAnswerControl"),
    source.indexOf("export function StudentPracticePage()"),
  );
  assert.match(controls, /question\.type === "single"[\s\S]*?<legend>单项选择<\/legend>/);
  assert.match(controls, /question\.type === "multiple"[\s\S]*?<legend>多项选择<\/legend>/);
  assert.match(controls, /question\.type === "true_false"[\s\S]*?<legend>判断题<\/legend>/);
  assert.match(controls, /checked=\{answer === option\.value\}/, "boolean false remains a selectable answer");
  assert.match(controls, /此复习题型不支持答案验证；只能关闭任务，不会提交答案或形成学习证据/);
  assert.match(practice, /此复习题型不支持答案验证；只能在可复习时间后无答案关闭，不会形成学习证据/);
  assert.match(practice, /关闭复习任务（不提交答案）/);
});

test("Review exposes the due time, disables early verification, and guards the handler", () => {
  assert.match(source, /function reviewIsDue\(review: Review\)/);
  assert.match(source, /Date\.parse\(review\.due_at\)/);
  assert.match(practice, /可复习时间：/);
  assert.match(practice, /disabled=\{!response \|\| !due \|\| draftState === "saving"\}/);
  assert.match(practice, /aria-describedby=\{!due \? `review-due-\$\{review\.id\}` : undefined\}/);
  assert.match(practice, /尚未到可复习时间，届时可验证并完成/);
  assert.match(practice, /if \(!response \|\| !reviewIsDue\(task\)\) return/);
  assert.match(practice, /关闭复习任务（不提交答案）/);
  assert.match(practice, /尚未到可复习时间，届时可无答案关闭/);
});
