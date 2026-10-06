import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/StudentCourseSupportPages.tsx", import.meta.url),
  "utf8",
);
const practice = source.slice(
  source.indexOf("export function StudentPracticePage()"),
  source.indexOf("export function StudentGrowthPage()"),
);

test("Practice lists only practice assessments and only reviews from the route course", () => {
  assert.match(practice, /api<Assessment\[]>\(`\/courses\/\$\{courseId\}\/assessments`\)/);
  assert.match(practice, /assessmentResult\.value\.filter\(\(assessment\) => assessment\.purpose === "practice"\)/);
  assert.match(practice, /api<Review\[]>\("\/review-tasks\?due_only=false"\)/);
  assert.match(practice, /reviewResult\.value\.filter\(\(review\) => review\.course_id === courseId\)/);
});

test("future review tasks expose due guidance and cannot call the verify API", () => {
  assert.match(source, /function reviewIsDue\(review: Review\)/);
  assert.match(source, /Date\.parse\(review\.due_at\)/);
  assert.match(practice, /disabled=\{!reviewAnswers\[review\.id\] \|\| !due\}/);
  assert.match(practice, /尚未到复习时间，届时可验证并完成/);
  assert.match(practice, /api\(`\/review-tasks\/\$\{task\.id\}\/verify`/);
  assert.match(practice, /task\.version === undefined\) return/);
});

test("review completion removes the card and announces the saved result", () => {
  assert.match(practice, /setReviews\(\(items\) => items\.filter\(\(item\) => item\.id !== task\.id\)\)/);
  assert.match(practice, /复习答案已提交，服务端将记录延迟保持证据/);
  assert.match(practice, /className="status-banner" role="status" aria-live="polite"/);
});

test("the browser audit covers the seeded wrong answer, purpose guard, and due-task policy", () => {
  const browser = fs.readFileSync(
    new URL("./student-practice-review-browser.cjs", import.meta.url),
    "utf8",
  );
  assert.match(browser, /合成练习：实验变量辨析（图表版）/);
  assert.match(browser, /const questionStem/);
  assert.match(browser, /B\. 因变量/);
  assert.match(browser, /purpose: "formal"/);
  assert.match(browser, /尚未到复习时间/);
  assert.match(browser, /复习答案已提交/);
});
