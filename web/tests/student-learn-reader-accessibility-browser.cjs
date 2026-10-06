/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.UI013_APP_ORIGIN ?? "http://127.0.0.1:3001";
const browserPath = process.env.UI013_CHROME_PATH;
const courseId = "01M00000000000000000000101";
const otherCourseId = "01M00000000000000000000109";
const sessionId = "01M00000000000000000000102";
const otherSessionId = "01M00000000000000000000110";
const pointerId = "01M00000000000000000000103";
const selectionStorageKey = "student-learn-selection-context";
const viewportWidths = [360, 393, 768];
const envelope = (data) => ({ data, meta: { request_id: "ui013-mock", server_time: "2026-10-06T00:00:00Z" } });
const businessWrites = [];

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: viewportWidths[0], height: 800 } });
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
    } else if ((path === `/api/v1/courses/${courseId}/materials` || path === `/api/v1/courses/${otherCourseId}/materials`) && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === "/api/v1/student/intervention-runs" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if ((path === `/api/v1/chat/sessions/${sessionId}` || path === `/api/v1/chat/sessions/${otherSessionId}`) && request.method() === "GET") {
      const isCurrentCourse = path.endsWith(sessionId);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        id: isCurrentCourse ? sessionId : otherSessionId,
        course_id: isCurrentCourse ? courseId : otherCourseId,
        mode: "course_qa",
        turns: isCurrentCourse ? [{ role: "tutor", content: "Synthetic saved answer.", citations: [{ evidence_pointer_id: pointerId, label: "Synthetic saved citation" }] }] : [],
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
    try {
      await page.waitForURL((url) => url.pathname === "/student", { timeout: 15_000 });
    } catch (error) {
      console.error(`Mock login did not reach /student; current URL=${page.url()}, visible error=${await page.locator(".form-error").textContent().catch(() => "none")}`);
      throw error;
    }

    const drawer = page.getByRole("dialog", { name: "教材来源快照" });
    for (const width of viewportWidths) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(`${appOrigin}/student/courses/${courseId}/learn?session_id=${sessionId}`);
      const citationTrigger = page.getByRole("button", { name: "打开引用", exact: true });
      await citationTrigger.waitFor({ state: "visible", timeout: 15_000 });
      await citationTrigger.click();
      await drawer.waitFor({ state: "visible" });
      assert.equal(await drawer.getByText("Synthetic pointer excerpt", { exact: true }).count(), 1);
      const geometry = await drawer.evaluate((node) => ({
        drawerWidth: node.getBoundingClientRect().width,
        drawerContentWidth: node.scrollWidth,
        drawerClientWidth: node.clientWidth,
        viewport: window.innerWidth,
        document: document.documentElement.scrollWidth,
      }));
      assert.ok(geometry.drawerWidth <= geometry.viewport && geometry.drawerContentWidth <= geometry.drawerClientWidth && geometry.document <= geometry.viewport,
        `${width}px Reader has no horizontal overflow: ${JSON.stringify(geometry)}`);
      const closeButton = drawer.getByRole("button", { name: "关闭上下文面板", exact: true });
      assert.equal(await closeButton.evaluate((node) => node === document.activeElement), true,
        `${width}px focus enters Reader at its close control`);
      await page.keyboard.press("Shift+Tab");
      assert.equal(await closeButton.evaluate((node) => node === document.activeElement), true,
        `${width}px reverse traversal remains in the dialog`);
      await page.keyboard.press("Tab");
      assert.equal(await closeButton.evaluate((node) => node === document.activeElement), true,
        `${width}px forward traversal remains in the dialog`);
      await page.keyboard.press("Escape");
      await drawer.waitFor({ state: "hidden" });
      assert.equal(await citationTrigger.evaluate((node) => node === document.activeElement), true,
        `${width}px close returns focus to the citation trigger`);
      await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });

      const stored = await page.evaluate((key) => sessionStorage.getItem(key), selectionStorageKey);
      assert.equal(stored, JSON.stringify({ course_id: courseId, evidence_pointer_id: pointerId }),
        `${width}px storage contains only the route course and persistent pointer ID`);
      assert.deepEqual(Object.keys(JSON.parse(stored)).sort(), ["course_id", "evidence_pointer_id"]);
      const readsBeforeRefresh = pointerReads;
      await page.reload();
      await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).waitFor({ state: "visible" });
      assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), selectionStorageKey), stored,
        `${width}px refresh retains only the ID payload`);
      assert.equal(pointerReads, readsBeforeRefresh, `${width}px refresh does not cache or eagerly reload pointer metadata`);

      await page.getByRole("button", { name: "重新打开所选来源", exact: true }).click();
      await drawer.waitFor({ state: "visible" });
      await drawer.getByText("Synthetic pointer excerpt", { exact: true }).waitFor({ state: "visible" });
      assert.equal(pointerReads, readsBeforeRefresh + 1, `${width}px reopening performs a fresh authorized pointer GET`);
      await page.keyboard.press("Escape");
      await drawer.waitFor({ state: "hidden" });
      assert.equal(await page.locator(".learn-turn").count(), 1, `${width}px return handoff creates no Tutor turn`);

      await page.goto(`${appOrigin}/student/courses/${otherCourseId}/learn?session_id=${otherSessionId}`);
      await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
      assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), selectionStorageKey), null,
        `${width}px changing courses clears the previous pointer context`);
      assert.equal(await page.getByText("已将一个固定教材来源带回当前学习上下文。", { exact: true }).count(), 0,
        `${width}px another course never displays the previous pointer context`);
    }
    assert.deepEqual(businessWrites, [], "mocked Reader/refresh/course-switch flow performs no business write");
    assert.deepEqual(pageErrors, []);
    console.log(`PASS UI-017 mocked browser harness: ${viewportWidths.join("/")}px Reader geometry and keyboard, ID-only refresh/re-GET, course isolation, zero business writes`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
