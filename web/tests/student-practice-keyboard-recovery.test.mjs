import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const pageSource = fs.readFileSync(
  new URL("../components/StudentCourseSupportPages.tsx", import.meta.url),
  "utf8",
);
const practice = pageSource.slice(
  pageSource.indexOf("export function StudentPracticePage()"),
  pageSource.indexOf("export function StudentGrowthPage()"),
);

test("Practice counts false and nonempty values as valid answers", () => {
  assert.match(pageSource, /function hasPracticeAnswer\(answer: PracticeAnswer\): boolean/);
  assert.match(pageSource, /if \(typeof answer === "boolean"\) return true/);
  assert.match(pageSource, /if \(Array\.isArray\(answer\)\) return answer\.length > 0/);
  assert.match(pageSource, /typeof answer === "string" && answer\.trim\(\)\.length > 0/);
  assert.match(practice, /Object\.values\(answers\)\.filter\(hasPracticeAnswer\)\.length/);
  assert.match(practice, /!hasPracticeAnswer\(answers\[item\.question_version_id\]\)/);
  assert.match(practice, /hasPracticeAnswer\(answers\[item\.question_version_id\]\) \? "已保存" : "尚未作答"/);
});

test("failed saves stay accessible, block submit, and can recover only from server attempt answers", () => {
  assert.match(practice, /setSaveState\(\(items\) => \(\{ \.\.\.items, \[questionId\]: "error" \}\)\)/);
  assert.match(practice, /saveFailed && <p role="alert">答案保存失败，请修改或重试后再提交。<\/p>/);
  assert.match(practice, /disabled=\{savePending \|\| saveFailed\}/);
  assert.match(practice, /attempt\.answers/);
  assert.match(practice, /questionType === "single" \? selected\[0\] \?\? "" : selected/);
  assert.match(practice, /setAnswers\(restoredAnswers\)/);
  assert.doesNotMatch(practice, /localStorage|sessionStorage/);
});

test("mock browser covers five keyboard input types, one failed PUT, refresh restore, and retry", () => {
  const browser = fs.readFileSync(
    new URL("./student-practice-keyboard-recovery-browser.cjs", import.meta.url),
    "utf8",
  );
  for (const type of ["single", "multiple", "true_false", "short_answer", "essay"]) {
    assert.match(browser, new RegExp(`type: "${type}"`));
  }
  assert.match(browser, /page\.keyboard\.press\("Space"\)/);
  assert.match(browser, /pressSequentially\("typed short response"\)/);
  assert.match(browser, /pressSequentially\("typed essay response"\)/);
  assert.match(browser, /respond\(route, 503,/);
  assert.match(browser, /page\.reload\(\)/);
  assert.match(browser, /第一次失败不能修改 mock 服务端 attempt/);
  assert.match(browser, /刷新后未保存的本地 B 不得残留或显示成功/);
  assert.match(browser, /assert\.deepEqual\(unexpectedRequests, \[\]/);
  assert.match(browser, /businessWrites\.every/);
});
