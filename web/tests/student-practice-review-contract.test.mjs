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
  assert.match(source, /function reviewQuestionSupportsVerification\(review: Review\)/);
  assert.match(source, /review\.question\.type === "single" \|\| review\.question\.type === "multiple"/);
  assert.match(source, /question\.type === "true_false"/);
  assert.match(source, /typeof answer === "boolean" \? \{ selected_keys: answer \}/);
  assert.match(source, /question\.type === "single"[\s\S]*?selected_keys: \[answer\]/);
  assert.match(source, /question\.type === "multiple"[\s\S]*?selected_keys: \[\.\.\.new Set\(answer\)\]/);
  assert.match(practice, /disabled=\{!response \|\| !due \|\| draftState === "saving"\}/);
  assert.match(practice, /aria-describedby=\{!due \? `review-due-\$\{review\.id\}` : undefined\}/);
  assert.match(practice, /id=\{`review-due-\$\{review\.id\}`\} role="status"/);
  assert.match(practice, /data-review-task-id=\{review\.id\}/);
  assert.match(practice, /可复习时间：/);
  assert.match(practice, /尚未到可复习时间，届时可验证并完成/);
  assert.match(practice, /api<\{ event_id: string; pending_qualification: boolean \}>\(\s*`\/review-tasks\/\$\{task\.id\}\/verify`/);
  assert.match(practice, /if \(!response \|\| !reviewIsDue\(task\)\) return/);
  assert.match(practice, /body: JSON\.stringify\(\{ version: reviewVersions\.current\[task\.id\] \?\? task\.version, response \}\)/);
});

test("review completion removes the card and announces the saved result", () => {
  assert.match(practice, /setReviews\(\(items\) => items\.filter\(\(item\) => item\.id !== task\.id\)\)/);
  assert.match(practice, /复习答案已提交，学习记录正在等待资格判定/);
  assert.match(practice, /未通过学习证据资格确认；成长信息未更新/);
  assert.match(practice, /复习学习记录已失效；成长信息未更新/);
  assert.match(practice, /if \(isReviewEvidenceQualified\(status\)\)/);
  assert.match(practice, /进入成长页时会重新读取当前信息/);
  assert.match(source, /复习任务已按无答案方式关闭；未提交答案或形成学习证据/);
  assert.match(practice, /className="status-banner" role="status" aria-live="polite"/);
});

test("the browser audit covers the seeded wrong answer, purpose guard, and due-task policy", () => {
  const browser = fs.readFileSync(
    new URL("./student-practice-review-browser.cjs", import.meta.url),
    "utf8",
  );
  assert.match(browser, /合成练习：实验变量辨析（五题版）/);
  assert.match(browser, /items\.length, 5/);
  assert.match(browser, /"single", "multiple", "true_false", "short_answer", "essay"/);
  assert.match(browser, /const questionStem/);
  assert.match(browser, /B\. 因变量/);
  assert.match(browser, /purpose: "formal"/);
  assert.match(browser, /UI005_RESUME_SYNTHETIC_ATTEMPT === "true"/);
  assert.match(browser, /assert\.ok\(!activeAttemptId \|\| resumeSyntheticAttempt/);
  assert.match(browser, /businessWrites/);
  assert.match(browser, /selected_keys, \["B"\]/);
  assert.match(browser, /新 attempt 对五题执行五次保存，多选题的两次勾选分别保存/);
  assert.match(browser, /savedAnswers.size, 5/);
  assert.match(browser, /verifyWrites\.length/);
  assert.match(browser, /尚未到可复习时间/);
  assert.match(browser, /复习答案已提交/);
});
