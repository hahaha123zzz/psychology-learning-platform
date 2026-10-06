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

test("Growth shows last-evidence source, time, dimension, and independence without inventing a cause", () => {
  assert.match(support, /type GrowthLastEvidence = \{ source_type\?: string \| null; created_at\?: string \| null; dimension\?: string \| null; independence_status\?: string \| null \}/);
  assert.match(growth, /GrowthEvidenceMetadata evidence=\{focus\.last_evidence\}/);
  assert.match(growth, /const tabKnowledgeByPoint = new Map\(\(tabs\?\.knowledge \?\? \[\]\)\.map/);
  assert.match(growth, /GrowthEvidenceMetadata evidence=\{tabKnowledgeByPoint\.get\(item\.knowledge_point\)\?\.last_evidence\}/);
  for (const label of ["来源：", "时间：", "维度：", "独立性："]) assert.ok(support.includes(label));
  assert.match(support, /不可用或已过期（原因未提供）/);
  assert.match(growth, /tab === "skills" && <p className="empty-state">当前服务端只有知识点掌握记录，没有独立技能证据/);
  assert.doesNotMatch(growth, /setSkills|skills\.push|skills:.*knowledge/);
});

test("Growth evidence browser audit uses synthetic metadata and proves read-only fail-closed rendering", () => {
  const browser = fs.readFileSync(new URL("./student-growth-evidence-browser.cjs", import.meta.url), "utf8");
  assert.match(browser, /const metadata = \{[\s\S]*source_type: "practice"[\s\S]*dimension: "apply"/);
  assert.match(browser, /last_evidence: null/);
  assert.match(browser, /不可用或已过期（原因未提供）/);
  assert.match(browser, /private tutor|correctness secret/i);
  assert.match(browser, /assert\.deepEqual\(writes, \[\]/);
});

test("Growth shows mutually exclusive hint-support raw counts and fails closed without scoring or adaptation", () => {
  const evidenceBrowser = fs.readFileSync(new URL("./student-growth-evidence-browser.cjs", import.meta.url), "utf8");
  assert.match(support, /hint_support_summary\?: \{ attempt_count: number; supported_attempt_count: number; independent_attempt_count: number; other_attempt_count: number \} \| null/);
  assert.match(support, /Number\.isFinite\(count\) && Number\.isInteger\(count\) && count >= 0/);
  for (const field of ["attempt_count", "supported_attempt_count", "independent_attempt_count", "other_attempt_count"]) {
    assert.match(support, new RegExp(`summary\\.${field}`));
  }
  assert.match(support, /summary\.attempt_count === 0[\s\S]*暂无足够记录/);
  assert.match(support, /summary == null[\s\S]*暂无足够记录/);
  assert.match(support, /次数统计不可用/);
  assert.match(growth, /GrowthHintSupportCard summary=\{tabs\?\.hint_support_summary\}/);
  assert.doesNotMatch(support, /hint_support_summary[^\n]*(?:percent|percentage|%|适配|建议)/i);
  assert.match(evidenceBrowser, /attempt_count: 3,[\s\S]*supported_attempt_count: 1,[\s\S]*independent_attempt_count: 1,[\s\S]*other_attempt_count: 1/);
  assert.match(evidenceBrowser, /attempt_count: 0, supported_attempt_count: 0, independent_attempt_count: 0, other_attempt_count: 0/);
  assert.match(evidenceBrowser, /hintSummary = null/);
  assert.match(evidenceBrowser, /independent_attempt_count: 0 \}/);
  assert.match(evidenceBrowser, /Number\.POSITIVE_INFINITY/);
  assert.match(evidenceBrowser, /supported_attempt_count: -1/);
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
  assert.match(browser, /businessWrites\.filter\(\(item\) => item\.method === "PATCH" && item\.path === "\/api\/v1\/me\/preferences"\)\.length, 2/);
  assert.match(browser, /businessWrites\.length, 3/);
  assert.match(browser, /UI006_STUDENT_PASSWORD/);
  assert.doesNotMatch(browser, /student-demo-local-only-20261005/);
});

test("the synthetic browser proves saved preference changes the next existing course-QA Tutor turn", () => {
  assert.match(browser, /UI006_COURSEQA_SESSION_ID/);
  assert.match(browser, /savedSession\.body\.data\.course_id, courseId/);
  assert.match(browser, /savedSession\.body\.data\.mode, "course_qa"/);
  assert.match(browser, /savedSession\.body\.data\.status, "active"/);
  assert.match(browser, /\/student\/courses\/\$\{courseId\}\/learn\?session_id=/);
  assert.match(browser, /targetResponseLength = "CONCISE"/);
  assert.match(browser, /targetExampleOrder = "EXAMPLE_FIRST"/);
  assert.match(browser, /baselinePreferences\.response_length !== targetResponseLength \|\| baselinePreferences\.example_order !== targetExampleOrder/);
  assert.match(browser, /variable example study time recall/);
  assert.match(browser, /assert\.match\(presentationAnswer, \/\^根据教材：For example,/);
  assert.match(browser, /presentationAnswer\.split\(\/\(\?<\=\[.!\?\]\)\\s\+\/u\)\.filter\(Boolean\)\.length, 1/);
  assert.match(browser, /method\(\) === "GET"/);
  assert.match(browser, /\/api\/v1\/chat\/sessions\/\$\{courseQaSessionId\}\/turns/);
  assert.match(browser, /item\.method === "POST" && item\.path === `\/api\/v1\/chat\/sessions\/\$\{courseQaSessionId\}\/turns`/);
  assert.match(browser, /businessWrites\.length, 3/);
  assert.match(browser, /preference_changed_next_tutor_presentation: preferencePresentationVerified/);
});
