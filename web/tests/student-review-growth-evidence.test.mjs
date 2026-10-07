import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { isReviewEvidenceQualified, waitForReviewQualification } from "../lib/review-evidence.ts";

const component = await readFile(new URL("../components/StudentCourseSupportPages.tsx", import.meta.url), "utf8");
const learningEvents = await readFile(new URL("../lib/learning-events.ts", import.meta.url), "utf8");

function event(id, courseId, qualificationStatus) {
  return { id, course_id: courseId, qualification_status: qualificationStatus };
}

test("review polling recognizes only the matching event in the requested course", async () => {
  assert.match(learningEvents, /LearningEventSource = .*\| "review"/);
  assert.equal(await waitForReviewQualification("event-1", "course-1", async () => [event("event-1", "course-1", "qualified")]), "qualified");
  assert.equal(await waitForReviewQualification("event-1", "course-1", async () => [event("event-1", "course-1", "rejected")]), "rejected");
  assert.equal(await waitForReviewQualification("event-1", "course-1", async () => [event("event-1", "course-1", "invalidated")]), "invalidated");
  assert.equal(await waitForReviewQualification("event-1", "course-1", async () => [event("event-1", "course-2", "qualified")], { attempts: 1 }), "pending");
});

test("pending qualification polling is bounded", async () => {
  let reads = 0;
  const status = await waitForReviewQualification("event-1", "course-1", async () => {
    reads += 1;
    return [event("event-1", "course-1", "pending")];
  }, { attempts: 3, intervalMs: 0, sleep: async () => {} });
  assert.equal(status, "pending");
  assert.equal(reads, 3);
});

test("only qualified review evidence promises Growth data on the next Growth-page load", () => {
  assert.equal(isReviewEvidenceQualified("qualified"), true);
  assert.equal(isReviewEvidenceQualified("pending"), false);
  assert.equal(isReviewEvidenceQualified("rejected"), false);
  assert.equal(isReviewEvidenceQualified("invalidated"), false);
  assert.match(component, /复习记录已通过资格确认；进入成长页时会重新读取当前信息/);
  assert.doesNotMatch(component, /reviewEvidenceQualifiedEvent|dispatchEvent|addEventListener\(.*Growth/);
  assert.match(component, /useEffect\(\(\) => \{ Promise\.all\(\[api<\{ focus:.*student\/growth\/overview/s);
  assert.match(component, /api<GrowthTabs>\(`\/student\/growth\/tabs\?course_id=\$\{courseId\}`\)/);
});

test("review states stay honest and plain completion makes no evidence claim", () => {
  assert.match(component, /reviewQuestionSupportsVerification\(review\)/);
  assert.match(component, /onClick=\{\(\) => void completeReview\(review\)\}/);
  assert.match(component, /复习任务已关闭；此操作未提交答案，也未形成学习证据/);
  assert.match(component, /复习答案已提交，学习记录仍在处理中；确认完成前成长信息不会更新/);
  assert.match(component, /未通过学习证据资格确认；成长信息未更新/);
  assert.match(component, /复习学习记录已失效；成长信息未更新/);
});
