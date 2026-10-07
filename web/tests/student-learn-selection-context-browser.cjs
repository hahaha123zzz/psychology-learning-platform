/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.UI014_APP_ORIGIN ?? "http://127.0.0.1:3001";
const browserPath = process.env.UI014_CHROME_PATH;
const courseA = "01M00000000000000000000201";
const courseB = "01M00000000000000000000202";
const sessionA = "01M00000000000000000000203";
const sessionB = "01M00000000000000000000204";
const pointerId = "01M00000000000000000000205";
const storageKey = "student-learn-selection-context";
const envelope = (data) => ({ data, meta: { request_id: "ui014-mock", server_time: "2026-10-06T00:00:00Z" } });

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const businessWrites = [];
  const pointerReads = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET" && !request.url().endsWith("/auth/login")) {
      businessWrites.push({ method: request.method(), path: new URL(request.url()).pathname });
    }
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname === `/api/v1/evidence-pointers/${pointerId}` && response.request().method() === "GET") {
      pointerReads.push(response.status());
    }
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/login" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ display_name: "Synthetic learner", platform_roles: [] })) });
    } else if ((path === `/api/v1/courses/${courseA}/materials` || path === `/api/v1/courses/${courseB}/materials`) && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === "/api/v1/student/intervention-runs" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if ((path === `/api/v1/chat/sessions/${sessionA}` || path === `/api/v1/chat/sessions/${sessionB}`) && request.method() === "GET") {
      const courseId = path.endsWith(sessionA) ? courseA : courseB;
      const turns = courseId === courseA
        ? [{ role: "tutor", content: "Synthetic saved answer.", citations: [{ evidence_pointer_id: pointerId, label: "Synthetic saved citation" }] }]
        : [];
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ id: path.endsWith(sessionA) ? sessionA : sessionB, course_id: courseId, mode: "course_qa", turns })) });
    } else if (path === `/api/v1/evidence-pointers/${pointerId}` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        evidence_pointer_id: pointerId,
        course_id: courseA,
        material_title: "Synthetic material",
        material_id: "01M00000000000000000000206",
        material_version_id: "01M00000000000000000000207",
        publication_snapshot_id: "01M00000000000000000000208",
        index_job_id: "01M00000000000000000000209",
        domain_release_id: "01M00000000000000000000210",
        chapter_path: "Synthetic chapter",
        physical_page: null,
        object_type: "paragraph",
        coordinate_space: "unavailable",
        bbox: null,
        anchors: [],
        excerpt: "Synthetic pointer excerpt",
        excerpt_sha256: "synthetic-only",
      })) });
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "Unexpected mock route" } }) });
    }
  });

  try {
    await page.goto(`${appOrigin}/login`);
    await page.getByLabel("邮箱").fill("synthetic@student.invalid");
    await page.getByLabel("密码").fill("synthetic-only");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/student", { timeout: 15_000 });

    await page.goto(`${appOrigin}/student/courses/${courseA}/learn?session_id=${sessionA}`);
    const citation = page.getByRole("button", { name: "打开引用", exact: true });
    await citation.waitFor({ state: "visible", timeout: 15_000 });
    await citation.click();
    const reader = page.getByRole("dialog", { name: "资料来源" });
    await reader.waitFor({ state: "visible" });
    await reader.getByText("Synthetic pointer excerpt", { exact: true }).waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });

    const stored = await page.evaluate((key) => sessionStorage.getItem(key), storageKey);
    assert.equal(stored, JSON.stringify({ course_id: courseA, evidence_pointer_id: pointerId }), "storage contains exactly course_id and persistent pointer ID");
    assert.deepEqual(Object.keys(JSON.parse(stored)).sort(), ["course_id", "evidence_pointer_id"]);
    assert.equal(pointerReads.length, 1);

    await page.reload();
    await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(pointerReads.length, 1, "refresh restores only the ID and does not fetch pointer metadata until Reader opens");
    await page.getByRole("button", { name: "重新打开所选来源", exact: true }).click();
    await reader.waitFor({ state: "visible" });
    await reader.getByText("Synthetic pointer excerpt", { exact: true }).waitFor({ state: "visible" });
    assert.equal(pointerReads.length, 2, "re-open performs a fresh Reader GET");
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });

    await page.getByRole("button", { name: "清除选择", exact: true }).click();
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), null, "clear removes the persisted selection");
    assert.equal(await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).count(), 0);

    await citation.click();
    await reader.waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });
    await page.goto(`${appOrigin}/student/courses/${courseB}/learn?session_id=${sessionB}`);
    await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), null, "course switch removes the previous course selection");
    assert.equal(await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).count(), 0, "other course never renders the previous course selection");
    assert.deepEqual(businessWrites, [], "only mocked auth and GET requests occur; no Tutor/business writes");
    assert.deepEqual(pageErrors, []);
    console.log("PASS UI-014 mocked browser: exact ID-only storage survives refresh, Reader re-fetches, clear/course switch remove it, zero business writes");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
