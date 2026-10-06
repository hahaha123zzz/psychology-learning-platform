/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.UI013_APP_ORIGIN ?? "http://127.0.0.1:3001";
const browserPath = process.env.UI013_CHROME_PATH;
const courseId = "01M00000000000000000000101";
const sessionId = "01M00000000000000000000102";
const pointerId = "01M00000000000000000000103";
const envelope = (data) => ({ data, meta: { request_id: "ui013-mock", server_time: "2026-10-06T00:00:00Z" } });
const businessWrites = [];

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 360, height: 800 } });
  const pageErrors = [];
  let pointerReads = 0;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname === `/api/v1/evidence-pointers/${pointerId}` && response.request().method() === "GET") pointerReads += 1;
  });
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET" && !request.url().endsWith("/auth/login")) {
      businessWrites.push({ method: request.method(), path: new URL(request.url()).pathname });
    }
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/login" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ display_name: "Synthetic learner", platform_roles: [] })) });
    } else if (path === `/api/v1/courses/${courseId}/materials` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === "/api/v1/student/intervention-runs" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === `/api/v1/chat/sessions/${sessionId}` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        id: sessionId,
        course_id: courseId,
        mode: "course_qa",
        turns: [{ role: "tutor", content: "Synthetic saved answer.", citations: [{ evidence_pointer_id: pointerId, label: "Synthetic saved citation" }] }],
      })) });
    } else if (path === `/api/v1/evidence-pointers/${pointerId}` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        evidence_pointer_id: pointerId,
        course_id: courseId,
        material_title: "Synthetic material",
        material_id: "01M00000000000000000000104",
        material_version_id: "01M00000000000000000000105",
        publication_snapshot_id: "01M00000000000000000000106",
        index_job_id: "01M00000000000000000000107",
        domain_release_id: "01M00000000000000000000108",
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

    await page.goto(`${appOrigin}/student/courses/${courseId}/learn?session_id=${sessionId}`);
    const citationTrigger = page.getByRole("button", { name: "打开引用", exact: true });
    await citationTrigger.waitFor({ state: "visible", timeout: 15_000 });
    await citationTrigger.click();
    const drawer = page.getByRole("dialog", { name: "教材来源快照" });
    await drawer.waitFor({ state: "visible" });
    assert.equal(await drawer.getByText("Synthetic pointer excerpt", { exact: true }).count(), 1);
    const narrowDrawer = await drawer.evaluate((node) => ({ width: node.getBoundingClientRect().width, viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    assert.ok(narrowDrawer.width <= narrowDrawer.viewport && narrowDrawer.document <= narrowDrawer.viewport,
      `360px Reader stays within the viewport: ${JSON.stringify(narrowDrawer)}`);
    assert.equal(await drawer.getByRole("button", { name: "关闭上下文面板", exact: true }).evaluate((node) => node === document.activeElement), true,
      "focus enters Reader at its close control");
    await page.keyboard.press("Shift+Tab");
    assert.equal(await drawer.getByRole("button", { name: "关闭上下文面板", exact: true }).evaluate((node) => node === document.activeElement), true,
      "reverse traversal remains within the modal when close is the only control");
    await page.keyboard.press("Tab");
    assert.equal(await drawer.getByRole("button", { name: "关闭上下文面板", exact: true }).evaluate((node) => node === document.activeElement), true,
      "forward traversal remains within the modal when close is the only control");
    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    assert.equal(await citationTrigger.evaluate((node) => node === document.activeElement), true,
      "Reader close returns keyboard focus to the citation trigger in Learn");
    await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });
    const selectionTrigger = page.getByRole("button", { name: "重新打开所选来源", exact: true });
    await selectionTrigger.click();
    await drawer.waitFor({ state: "visible" });
    assert.equal(pointerReads, 2, "the selected context retains only its pointer ID and Reader GET reauthorizes it on reopening");
    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    assert.equal(await page.locator(".learn-turn").count(), 1, "return handoff creates no Tutor turn");
    assert.deepEqual(businessWrites, [], "mocked return-to-Learn flow performs no business write");

    const narrow = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      pageWidth: document.querySelector(".student-learn-page")?.scrollWidth,
    }));
    assert.ok(narrow.documentWidth <= narrow.viewportWidth, `no horizontal document overflow: ${JSON.stringify(narrow)}`);
    assert.deepEqual(pageErrors, []);
    console.log("PASS UI-013 mocked browser harness: Reader re-fetch, Escape/Shift+Tab, focus return, ID-only SelectionContext message, 360px no-overflow, zero business writes");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
