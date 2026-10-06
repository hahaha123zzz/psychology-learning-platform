/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.UI030_APP_ORIGIN ?? "http://127.0.0.1:3001";
const browserPath = process.env.UI030_CHROME_PATH;
const courseId = "01M00000000000000000000301";
const sessionId = "01M00000000000000000000302";
const pointerId = "01M00000000000000000000303";
const failurePointerId = "01M00000000000000000000304";
const missingPointerId = "01M00000000000000000000305";
const envelope = (data) => ({ data, meta: { request_id: "ui030-mock", server_time: "2026-10-07T00:00:00Z" } });
const labels = [
  ["textbook", "教材"], ["slides", "课件"], ["handout", "讲义"],
  ["exercise", "练习资料"], ["reference", "参考资料"], ["other", "课程资料"],
  ["unrecognized", "课程资料"],
];

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage();
  const pageErrors = [];
  const resourceWrites = [];
  const otherWrites = [];
  let pointerReadCount = 0;
  let readerReturns404 = false;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname === "/api/v1/learning-events") {
      resourceWrites.push(JSON.parse(request.postData() ?? "{}"));
    } else if (url.pathname.startsWith("/api/v1/") && request.method() !== "GET" && url.pathname !== "/api/v1/auth/login" && url.pathname !== "/api/v1/knowledge/search") {
      otherWrites.push(`${request.method()} ${url.pathname}`);
    }
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/login" && request.method() === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ display_name: "Synthetic learner", platform_roles: [] })) });
    } else if (path === "/api/v1/courses" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([{ id: courseId, title: "Synthetic course", term: "demo" }])) });
    } else if (path === `/api/v1/courses/${courseId}/materials` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([{ id: "01M00000000000000000000306", title: "Untyped synthetic title", current_version: { id: "01M00000000000000000000307", version_no: 1, status: "published" } }])) });
    } else if (path === "/api/v1/student/intervention-runs" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === `/api/v1/chat/sessions/${sessionId}` && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        id: sessionId, course_id: courseId, mode: "course_qa",
        turns: [{ role: "tutor", content: "Synthetic saved answer.", citations: [{ evidence_pointer_id: pointerId, label: "Saved citation", material_type: "slides" }] }],
      })) });
    } else if (path === "/api/v1/knowledge/search" && request.method() === "POST") {
      const items = labels.map(([material_type], index) => ({
        title: `Synthetic ${index}`, text: `Synthetic excerpt ${index}`, material_type,
        object_type: "paragraph", evidence_id: `synthetic-${index}`,
        ...(index === 0 ? { evidence_pointer_id: pointerId } : index === 1 ? { evidence_pointer_id: failurePointerId } : index === 2 ? { evidence_pointer_id: missingPointerId } : {}),
      }));
      items[6].material_type = "";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ items })) });
    } else if (path.startsWith("/api/v1/evidence-pointers/") && request.method() === "GET") {
      const requested = path.split("/").at(-1);
      if (requested === pointerId) pointerReadCount += 1;
      if (requested === missingPointerId || (requested === pointerId && readerReturns404)) {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { message: "Synthetic pointer unavailable" } }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
          evidence_pointer_id: requested,
          course_id: courseId,
          material_title: "Untyped synthetic title",
          material_type: requested === failurePointerId ? "reference" : "textbook",
          material_id: "01M00000000000000000000308", material_version_id: "01M00000000000000000000309",
          publication_snapshot_id: null, index_job_id: null, domain_release_id: null,
          chapter_path: "Synthetic chapter", physical_page: null, object_type: "paragraph",
          coordinate_space: "unavailable", bbox: null, anchors: [], excerpt: `Synthetic excerpt ${requested}`, excerpt_sha256: "synthetic-only",
        })) });
      }
    } else if (path === "/api/v1/learning-events" && request.method() === "POST") {
      const body = JSON.parse(request.postData() ?? "{}");
      await route.fulfill(body.evidence_pointer_id === failurePointerId
        ? { status: 500, contentType: "application/json", body: JSON.stringify({ error: { message: "Synthetic event failure" } }) }
        : { status: 201, contentType: "application/json", body: JSON.stringify(envelope({ id: "synthetic-event" })) });
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
    await page.getByRole("button", { name: "打开引用", exact: true }).waitFor({ state: "visible", timeout: 15_000 });

    await page.getByLabel("搜索教材").fill("synthetic query");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    for (const [, label] of labels) await page.getByText(label, { exact: true }).first().waitFor({ state: "visible" });
    assert.equal(await page.getByText("权威教材", { exact: true }).count(), 0, "labels never infer publisher or authority from a title");

    const drawer = page.getByRole("dialog", { name: "教材来源快照" });
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).first().click();
    await drawer.waitFor({ state: "visible" });
    await drawer.getByText("Synthetic excerpt " + pointerId, { exact: true }).waitFor({ state: "visible" });
    await drawer.getByText("教材", { exact: true }).waitFor({ state: "visible" });
    await page.waitForFunction(() => document.body.innerText.includes("Synthetic excerpt"));
    await page.waitForTimeout(50);
    assert.equal(resourceWrites.length, 1, "successful Reader open records once despite render/state updates");
    assert.deepEqual(Object.keys(resourceWrites[0]).sort(), ["course_id", "event_key", "evidence_pointer_id"]);
    assert.equal(resourceWrites[0].course_id, courseId);
    assert.equal(resourceWrites[0].evidence_pointer_id, pointerId);
    assert.ok(resourceWrites[0].event_key);
    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    readerReturns404 = true;
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).first().click();
    await drawer.waitFor({ state: "visible" });
    await drawer.getByText("Synthetic pointer unavailable", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await drawer.getByText("Synthetic excerpt " + pointerId, { exact: true }).count(), 0, "404 clears stale excerpt from the previous opening");
    assert.equal(resourceWrites.length, 1, "404 Reader GET does not record an event");

    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).nth(1).click();
    await drawer.waitFor({ state: "visible" });
    await drawer.getByText("Synthetic excerpt " + failurePointerId, { exact: true }).waitFor({ state: "visible" });
    await page.waitForTimeout(50);
    assert.equal(resourceWrites.length, 2, "event failure is attempted once");
    assert.equal(await drawer.getByText("Synthetic excerpt " + failurePointerId, { exact: true }).count(), 1, "event write failure does not block reading");
    assert.equal(await drawer.getByText(/已记录|记录成功/).count(), 0, "UI does not claim the failed event was recorded");

    await page.keyboard.press("Escape");
    await drawer.waitFor({ state: "hidden" });
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).nth(2).click();
    await drawer.getByText("Synthetic pointer unavailable", { exact: true }).waitFor({ state: "visible" });
    assert.equal(resourceWrites.length, 2, "initial 404 has no event write");
    assert.deepEqual(otherWrites, [], "no business writes beyond the explicitly allowed learning-event POST");
    assert.deepEqual(pageErrors, []);
    console.log(`PASS UI-030 mocked browser: material labels, successful single event, GET 404 no event/stale excerpt, event-write failure nonblocking; pointer GETs=${pointerReadCount}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
