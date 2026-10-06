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
const browser = fs.readFileSync(
  new URL("./student-review-verify-retry-browser.cjs", import.meta.url),
  "utf8",
);

test("failed Review verify keeps the task and selected answer available for retry", () => {
  const catchStart = practice.indexOf("} catch (reason) {", practice.indexOf("async function verifyReview"));
  const failedVerifyBranch = practice.slice(catchStart, practice.indexOf("setReviews((items)", catchStart));
  assert.match(failedVerifyBranch, /setNotice\(message\(reason\)\)/);
  assert.match(failedVerifyBranch, /return;/);
  assert.doesNotMatch(failedVerifyBranch, /setReviewAnswers|setReviews/);
  assert.match(practice, /className="status-banner" role="status" aria-live="polite"/);
});

test("mock browser injects one retryable failure then verifies accessible retry recovery", () => {
  assert.match(browser, /synthetic-review-ui026/);
  assert.match(browser, /verifyCalls === 1/);
  assert.match(browser, /SYNTHETIC_RETRYABLE_FAILURE/);
  assert.match(browser, /verifyCalls === 2/);
  assert.match(browser, /await answer\.selectOption\("A"\)/);
  assert.match(browser, /await answer\.inputValue\(\), "A"/);
  assert.match(browser, /getByRole\("status"\).*合成验证暂时失败/s);
  assert.match(browser, /assert\.equal\(await verify\.isEnabled\(\), true/);
  assert.match(browser, /await row\.waitFor\(\{ state: "detached" \}\)/);
  assert.match(browser, /复习记录已通过资格确认/);
  assert.match(browser, /verify_writes: writes\.length/);
  assert.match(browser, /assert\.deepEqual\(unexpectedRequests, \[\]/);
});
