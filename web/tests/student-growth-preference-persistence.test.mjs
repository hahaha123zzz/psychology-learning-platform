import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const support = read("../components/StudentCourseSupportPages.tsx");
const growth = support.slice(
  support.indexOf("export function StudentGrowthPage()"),
  support.indexOf("export function StudentMePage()"),
);
const preferences = read("../components/StudentPreferencesPanel.tsx");
const browser = read("./student-growth-preference-browser.cjs");

test("Growth reads course-scoped projections and filters the global review list to its route course", () => {
  assert.match(growth, /\/student\/growth\/overview\?course_id=\$\{courseId\}/);
  assert.match(growth, /\/student\/growth\/knowledge\?course_id=\$\{courseId\}/);
  assert.match(growth, /\/student\/growth\/tabs\?course_id=\$\{courseId\}/);
  assert.match(growth, /setDueCount\(overview\.attention\.due_review_count\)/);
  assert.match(growth, /setReviews\(nextReviews\.filter\(\(review\) => review\.course_id === courseId\)\)/);
  assert.match(growth, /focus\.state_reason/);
});

test("Preference loads the current values and saves with the server version", () => {
  assert.match(preferences, /api<Preferences>\("\/me\/preferences"\)/);
  assert.match(preferences, /api<Preferences>\("\/me\/preferences", \{ method: "PATCH"/);
  assert.match(preferences, /version: data\.version, \.\.\.draft/);
  assert.match(preferences, /value=\{p\.response_length\}/);
  assert.match(preferences, /value=\{p\.example_order\}/);
  assert.match(preferences, /偏好已保存/);
});

test("the browser flow restores the complete original preference snapshot in finally", () => {
  assert.match(browser, /const baselinePreferences/);
  assert.match(browser, /finally\s*\{/);
  const cleanup = browser.slice(browser.indexOf("} finally {"), browser.indexOf("await browser.close();"));
  assert.match(cleanup, /selectOption\(savedBaseline\.response_length\)/);
  assert.match(cleanup, /selectOption\(savedBaseline\.example_order\)/);
  assert.match(cleanup, /getByRole\("button", \{ name: "保存偏好"/);
  assert.match(cleanup, /await page\.reload\(\)/);
  assert.doesNotMatch(browser, /method:\s*"PATCH"|method:\s*"POST"|method:\s*"PUT"|method:\s*"DELETE"/);
  assert.match(browser, /assert\.deepEqual\(verified\.body\.data\.preferences, savedBaseline/);
  assert.match(browser, /\/student\/growth\/overview\?course_id=/);
  assert.match(browser, /response_length/);
  assert.match(browser, /example_order/);
  assert.match(browser, /UI-006 cross-course review guard/);
  assert.match(browser, /await route\.abort\(\)/);
  assert.doesNotMatch(browser, /\/me\/privacy\/delete-request/);
  assert.match(browser, /businessWrites\.length, 2/);
  assert.match(browser, /UI006_STUDENT_PASSWORD/);
  assert.doesNotMatch(browser, /student-demo-local-only-20261005/);
});
