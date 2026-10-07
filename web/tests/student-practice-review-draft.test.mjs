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
const saveDraft = practice.slice(
  practice.indexOf("async function saveReviewDraft"),
  practice.indexOf("async function reloadReviewDraft"),
);
const verify = practice.slice(
  practice.indexOf("async function verifyReview"),
  practice.indexOf("function saveResponse"),
);

test("Review list restores typed server draft and task version without creating an Assessment Attempt", () => {
  assert.match(source, /type ReviewDraftResponse = \{ selected_keys\?: string\[] \| boolean \}/);
  assert.match(source, /response_draft\?: ReviewDraftResponse \| null/);
  assert.match(source, /version: number; question\?: ReviewQuestion/);
  assert.match(source, /api<Review\[]>\("\/review-tasks\?due_only=false"\)/);
  assert.match(source, /reviewVersions\.current = Object\.fromEntries\(currentReviews\.map\(\(review\) => \[review\.id, review\.version\]\)\)/);
  assert.match(source, /reviewAnswerFromDraft\(review\)/);
  assert.match(source, /question\?\.type === "single"\) return selected\[0\] \?\? ""/);
  assert.match(source, /question\?\.type === "multiple"\) return selected/);
  assert.match(source, /typeof selected === "boolean" \? selected : undefined/);
  assert.match(source, /const currentAnswers = currentReviews\.reduce<Record<string, ReviewAnswer>>/);
  assert.match(source, /reviewDraftAnswers\.current = currentAnswers/);
});

test("incomplete answer drafts save deliberately with expected version and restore the returned version", () => {
  assert.match(saveDraft, /`\/review-tasks\/\$\{task\.id\}\/draft`/);
  assert.match(saveDraft, /method: "PUT"/);
  assert.match(saveDraft, /body: JSON\.stringify\(\{ version: reviewVersions\.current\[task\.id\] \?\? task\.version, response \}\)/);
  assert.match(saveDraft, /reviewVersions\.current\[task\.id\] = saved\.version/);
  assert.match(saveDraft, /response_draft: saved\.response_draft/);
  assert.match(saveDraft, /草稿未保存|复习答案草稿未保存/);
  assert.match(practice, /onBlur=\{\(\) => \{ if \(reviewDraftStates\[review\.id\] === "dirty"\) void saveReviewDraft\(review\); \}\}/);
  assert.match(practice, /onClick=\{\(\) => void saveReviewDraft\(review\)\}>保存答案草稿/);
  assert.match(practice, /未验证，也未形成学习证据/);
  assert.doesNotMatch(saveDraft, /attempts|\/attempts/);
});

test("verification first persists dirty drafts and submits the latest ReviewTask version", () => {
  assert.match(verify, /draftState === "dirty" \|\| draftState === "saving" \|\| draftState === "error"/);
  assert.match(verify, /body: JSON\.stringify\(\{ version: reviewVersions\.current\[task\.id\] \?\? task\.version, response \}\)/);
  assert.match(verify, /if \(!response \|\| !reviewIsDue\(task\)\) return/);
  assert.match(verify, /delete reviewVersions\.current\[task\.id\]/);
});

test("unsupported types close only after due time with expected version and explicit no-answer reason", () => {
  const close = practice.slice(
    practice.indexOf("async function completeReview"),
    practice.indexOf("async function verifyReview"),
  );
  assert.match(close, /if \(reviewQuestionSupportsVerification\(task\) \|\| !reviewIsDue\(task\)\) return/);
  assert.match(close, /`\/review-tasks\/\$\{task\.id\}\/complete`/);
  assert.match(close, /method: "POST"/);
  assert.match(close, /version: reviewVersions\.current\[task\.id\] \?\? task\.version, reason: "unsupported_question_type"/);
  assert.match(practice, /关闭复习任务（不提交答案）/);
  assert.match(practice, /可复习时间：/);
  assert.match(practice, /尚未到可复习时间，届时可无答案关闭/);
  assert.match(practice, /未提交答案或形成学习证据/);
});

test("stale draft recovery rereads only service state and fails closed on access errors", () => {
  const reload = practice.slice(
    practice.indexOf("async function reloadReviewDraft"),
    practice.indexOf("async function completeReview"),
  );
  assert.match(reload, /api<Review\[]>\("\/review-tasks\?due_only=false"\)/);
  assert.match(reload, /reviewAnswerFromDraft\(latest\)/);
  assert.match(reload, /currentReviews\.map\(\(item\) => \[item\.id, item\.version\]\)/);
  assert.match(reload, /reviewVersions\.current = \{\}/);
  assert.match(reload, /setReviews\(\[\]\)/);
  assert.match(reload, /无法重新读取复习任务/);
});
