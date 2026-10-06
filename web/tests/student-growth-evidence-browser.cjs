/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.GROWTH_EVIDENCE_APP_ORIGIN ?? "http://127.0.0.1:3128";
const browserPath = process.env.GROWTH_EVIDENCE_CHROME_PATH;
const courseId = "01M00000000000000000000301";
const userId = "01M00000000000000000000302";
const goodEvidenceId = "01M00000000000000000000303";
const otherKnowledgePoint = "chapter-1:learning";
const metadata = {
  evidence_id: goodEvidenceId,
  source_type: "practice",
  created_at: "2026-10-06T08:30:00+00:00",
  dimension: "apply",
  independence_status: "independent",
};
let hintSummary = {
  attempt_count: 3,
  supported_attempt_count: 1,
  independent_attempt_count: 1,
  other_attempt_count: 1,
};
const envelope = (data) => ({ data, meta: { request_id: "growth-evidence-mock", server_time: "2026-10-06T08:31:00Z" } });

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const writes = [];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET" && !request.url().endsWith("/auth/login")) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/auth/login" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ id: userId, display_name: "Synthetic learner", platform_roles: ["student"] })) });
    } else if (path === "/api/v1/courses" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([{ id: courseId, title: "Synthetic course", term: "Demo" }])) });
    } else if (path === "/api/v1/student/growth/overview" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        focus: { knowledge_point: "chapter-1:memory", state: "learning", state_reason: "Synthetic state", next_step: "Review", last_evidence: metadata },
        attention: { due_review_count: 0 },
        explainability_refs: [],
      })) });
    } else if (path === "/api/v1/student/growth/knowledge" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([
        { knowledge_point: "chapter-1:memory", state: "learning", evidence_count: 1, state_reason: "Synthetic", algorithm_version: "test", next_step: "Review", updated_at: "2026-10-06T08:30:00Z" },
        { knowledge_point: otherKnowledgePoint, state: "not_started", evidence_count: 0, state_reason: "No evidence", algorithm_version: "test", next_step: "Study", updated_at: "2026-10-06T08:30:00Z" },
      ])) });
    } else if (path === "/api/v1/student/growth/tabs" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        knowledge: [
          { knowledge_point: "chapter-1:memory", last_evidence: metadata },
          { knowledge_point: otherKnowledgePoint, last_evidence: null },
        ],
        skills: [],
        misconceptions: [],
        trajectory: [],
        hint_support_summary: hintSummary,
      })) });
    } else if (path === "/api/v1/review-tasks" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "UNEXPECTED_MOCK_ROUTE", message: path } }) });
    }
  });

  try {
    await page.goto(`${appOrigin}/login`);
    await page.getByLabel("邮箱").fill("synthetic@student.invalid");
    await page.getByLabel("密码").fill("synthetic-only");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/student", { timeout: 15_000 });
    await page.goto(`${appOrigin}/student/courses/${courseId}/growth`);

    await page.getByRole("heading", { name: "成长", exact: true }).waitFor({ state: "visible" });
    await page.getByText("来源：practice", { exact: true }).first().waitFor({ state: "visible" });
    await page.getByText("维度：apply", { exact: true }).first().waitFor({ state: "visible" });
    await page.getByText("独立性：independent", { exact: true }).first().waitFor({ state: "visible" });
    const hintCard = page.locator(".growth-hint-support");
    await hintCard.getByText("尝试总数：3", { exact: true }).waitFor({ state: "visible" });
    await hintCard.getByText("有支持尝试：1", { exact: true }).waitFor({ state: "visible" });
    await hintCard.getByText("独立尝试：1", { exact: true }).waitFor({ state: "visible" });
    await hintCard.getByText("其他尝试：1", { exact: true }).waitFor({ state: "visible" });
    hintSummary = { attempt_count: 0, supported_attempt_count: 0, independent_attempt_count: 0, other_attempt_count: 0 };
    await page.reload();
    await hintCard.getByText("尝试总数：0", { exact: true }).waitFor({ state: "visible" });
    await hintCard.getByText("暂无足够记录。", { exact: true }).waitFor({ state: "visible" });
    hintSummary = null;
    await page.reload();
    await hintCard.getByText("暂无足够记录。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await hintCard.locator("li").count(), 0, "empty summary shows no fabricated counts");
    hintSummary = { attempt_count: 1, supported_attempt_count: 1, independent_attempt_count: 0 };
    await page.reload();
    await hintCard.getByText("次数统计不可用。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await hintCard.locator("li").count(), 0, "missing counters fail closed");
    hintSummary = { attempt_count: 2, supported_attempt_count: 1, independent_attempt_count: 1, other_attempt_count: Number.POSITIVE_INFINITY };
    await page.reload();
    await hintCard.getByText("次数统计不可用。", { exact: true }).waitFor({ state: "visible" });
    hintSummary = { attempt_count: 2, supported_attempt_count: -1, independent_attempt_count: 1, other_attempt_count: 2 };
    await page.reload();
    await hintCard.getByText("次数统计不可用。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await hintCard.locator("li").count(), 0, "malformed counts fail closed");
    const unavailable = page.getByText("最近依据：不可用或已过期（原因未提供）", { exact: true });
    assert.ok(await unavailable.count() >= 1, "missing evidence metadata renders an explicit unavailable state");
    assert.equal(await page.getByText(/student answer|private tutor|correctness secret/i).count(), 0);
    await page.getByRole("tab", { name: "技能", exact: true }).click();
    await page.getByText("当前服务端只有知识点掌握记录，没有独立技能证据", { exact: false }).waitFor({ state: "visible" });
    assert.deepEqual(writes, [], "growth projection is read-only");
    assert.deepEqual(errors, []);
    console.log("PASS Growth evidence browser: scoped metadata fields, null fail-closed UI, no private content, skills not inferred, zero writes");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
