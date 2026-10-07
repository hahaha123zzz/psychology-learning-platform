/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const targetUrl = process.env.R3_UI_E2E_URL ?? "http://127.0.0.1:3002";
const email = process.env.R3_UI_E2E_EMAIL;
const password = process.env.R3_UI_E2E_PASSWORD;
const sessionId = process.env.R3_UI_E2E_SESSION_ID ?? "01M46AGA8A51F1K89VDYJVZRG7";
const requestedPointerId = process.env.R3_UI_E2E_POINTER_ID ?? "01M46AGAD13H4MS5V5G5D1TMQ6";
const browserPath = process.env.R3_UI_E2E_BROWSER ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";

if (!email || !password) {
  throw new Error("请提供隔离 synthetic 学生账号；不使用新建会话或假成功数据替代。");
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 10 });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const pageErrors = [];
  const forbiddenPosts = [];
  const readerResponses = [];
  const sessionReads = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${targetUrl}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });
    await page.goto(`${targetUrl}/student`);
    await page.getByRole("heading", { name: "继续你的学习" }).waitFor({ state: "visible" });
    await page.waitForFunction(() => Array.from(document.querySelectorAll('a[href^="/student/courses/"]'))
      .some((anchor) => /^\/student\/courses\/[^/]+$/.test(anchor.getAttribute("href") ?? "")), null, { timeout: 20_000 });
    const coursePath = await page.locator('a[href^="/student/courses/"]').evaluateAll((anchors) => anchors
      .map((anchor) => anchor.getAttribute("href"))
      .find((href) => href && /^\/student\/courses\/[^/]+$/.test(href)));
    assert.ok(coursePath, "Home should expose the student's authorized course");

    page.on("request", (request) => {
      const url = new URL(request.url());
      const sessionMatch = url.pathname.match(/\/api\/v1\/chat\/sessions\/([^/]+)$/);
      if (request.method() === "GET" && sessionMatch) sessionReads.push(decodeURIComponent(sessionMatch[1]));
      if (request.method() === "POST" && (
        url.pathname.endsWith("/knowledge/search")
        || url.pathname === "/api/v1/chat/sessions"
        || url.pathname.includes("/chat/sessions/") && url.pathname.endsWith("/turns")
      )) forbiddenPosts.push(`${request.method()} ${url.pathname}`);
    });
    page.on("response", (response) => {
      const url = new URL(response.url());
      if (url.pathname.includes("/evidence-pointers/") && response.request().method() === "GET") {
        readerResponses.push({ path: url.pathname, status: response.status() });
      }
    });

    const learnPath = `${coursePath}/learn`;
    await page.goto(`${targetUrl}${learnPath}`);
    await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
    await page.waitForFunction(() => !Array.from(document.querySelectorAll(".status-banner"))
      .some((banner) => banner.textContent?.includes("正在读取可学习资料")));
    assert.ok(await page.locator(".learn-material-row").count() > 0, "Learn should load its real authorized material list");
    assert.deepEqual(sessionReads, [], "without explicit session_id, Learn must not read a saved chat session");

    const savedMetadata = await page.evaluate(async ({ id, pointerId }) => {
      const response = await fetch(`/api/v1/chat/sessions/${encodeURIComponent(id)}`);
      const envelope = await response.json();
      if (!response.ok) throw new Error(`saved session GET failed: ${response.status}`);
      const saved = envelope.data;
      const citations = saved.turns
        .filter((turn) => turn.role === "tutor")
        .flatMap((turn) => Array.isArray(turn.citations) ? turn.citations : [])
        .filter((citation) => typeof citation.evidence_pointer_id === "string");
      const pointerIndex = citations.findIndex((item) => item.evidence_pointer_id === pointerId);
      const citation = pointerIndex >= 0 ? citations[pointerIndex] : citations[0];
      if (!citation) throw new Error("saved synthetic session has no citation pointer");
      const pointerResponse = await fetch(`/api/v1/evidence-pointers/${encodeURIComponent(citation.evidence_pointer_id)}`);
      const pointerEnvelope = await pointerResponse.json();
      if (!pointerResponse.ok) throw new Error(`saved pointer GET failed: ${pointerResponse.status}`);
      return {
        id: saved.id,
        courseId: saved.course_id,
        mode: saved.mode,
        turnCount: saved.turns.filter((turn) => turn.role === "student" || turn.role === "tutor").length,
        citationCount: citations.length,
        pointerIndex: pointerIndex >= 0 ? pointerIndex : 0,
        pointerId: citation.evidence_pointer_id,
        materialVersionId: pointerEnvelope.data.material_version_id,
        physicalPage: pointerEnvelope.data.physical_page,
      };
    }, { id: sessionId, pointerId: requestedPointerId });
    assert.equal(savedMetadata.id, sessionId);
    assert.equal(savedMetadata.courseId, coursePath.split("/")[3], "saved session must belong to Home's current course");
    assert.equal(savedMetadata.mode, "course_qa");
    assert.ok(savedMetadata.citationCount > 0);
    assert.ok(savedMetadata.materialVersionId);
    assert.ok(savedMetadata.physicalPage > 0);

    const learnUrl = `${targetUrl}${learnPath}?view=history&session_id=${encodeURIComponent(sessionId)}`;
    await page.goto(learnUrl);
    await page.locator(".learn-turn.tutor").first().waitFor({ state: "visible", timeout: 20_000 });
    const citationButton = page.getByRole("button", { name: "打开引用", exact: true }).first();
    await citationButton.waitFor({ state: "visible" });
    assert.ok(await page.locator(".learn-turn.student").count() > 0, "saved student turns should restore");
    assert.ok(await page.locator(".learn-turn.tutor").count() > 0, "saved tutor turns should restore");
    assert.equal(await page.locator(".learn-turn").count(), savedMetadata.turnCount);
    assert.equal(await page.getByRole("button", { name: "打开引用", exact: true }).count(), savedMetadata.citationCount);
    assert.equal(new URL(page.url()).searchParams.get("view"), "history");

    await page.reload();
    await page.locator(".learn-turn.tutor").first().waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await page.locator(".learn-turn").count(), savedMetadata.turnCount);
    assert.equal(await page.getByRole("button", { name: "打开引用", exact: true }).count(), savedMetadata.citationCount);
    assert.equal(new URL(page.url()).searchParams.get("view"), "history", "refresh must preserve unrelated query params");
    await page.getByRole("button", { name: "打开引用", exact: true }).nth(savedMetadata.pointerIndex).click();
    const dialog = page.getByRole("dialog", { name: "资料来源" });
    await dialog.waitFor({ state: "visible", timeout: 20_000 });
    await dialog.getByText(savedMetadata.materialVersionId, { exact: true }).waitFor({ state: "visible" });
    await dialog.getByRole("img", { name: new RegExp(`资料物理页 ${savedMetadata.physicalPage}`) }).waitFor({ state: "visible", timeout: 20_000 });
    assert.ok(readerResponses.some((item) => item.path.endsWith(`/evidence-pointers/${savedMetadata.pointerId}`) && item.status === 200), "saved pointer GET should succeed");
    assert.ok(readerResponses.some((item) => item.path.includes("/page-image") && item.status === 200), "pinned physical page image GET should succeed");
    console.log(`PASS restore/Reader: ${savedMetadata.turnCount} turns/${savedMetadata.citationCount} citations survive refresh; pointer ${savedMetadata.pointerId} opens pinned version ${savedMetadata.materialVersionId}, page ${savedMetadata.physicalPage}`);

    await page.goto(`${targetUrl}${coursePath}/learn?session_id=00000000000000000000000000`);
    await page.getByRole("status").filter({ hasText: "无法恢复该学习会话" }).waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await page.locator(".learn-turn").count(), 0, "unauthorized or missing session must show no turns or citations");
    assert.equal(await page.getByRole("button", { name: "打开引用", exact: true }).count(), 0);
    console.log("PASS unavailable session: visible error and no saved cards");

    await page.route("**/api/v1/chat/sessions/ui-mismatched-session", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data: {
          id: "ui-mismatched-session",
          course_id: "01M00000000000000000000000",
          mode: "course_qa",
          status: "active",
          turns: [{
            role: "tutor",
            content: "mismatch guard fixture",
            citations: [{ label: "mismatch citation", evidence_pointer_id: "01M00000000000000000000001" }],
          }],
        },
      }),
    }));
    await page.goto(`${targetUrl}${coursePath}/learn?session_id=ui-mismatched-session`);
    await page.getByRole("status").filter({ hasText: "无法恢复该学习会话" }).waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await page.locator(".learn-turn").count(), 0, "mismatched course response must fail closed");
    assert.equal(await page.getByRole("button", { name: "打开引用", exact: true }).count(), 0);
    assert.equal(await page.getByText("mismatch guard fixture", { exact: true }).count(), 0);
    console.log("PASS mismatched course: mocked negative response is rejected before turn or Reader cards render");

    assert.deepEqual(forbiddenPosts, [], "page load and Reader restore must not search, create sessions, or create Tutor turns");
    const allowedSessionIds = new Set([sessionId, "00000000000000000000000000", "ui-mismatched-session"]);
    assert.ok(sessionReads.every((id) => allowedSessionIds.has(id)), `only explicit session IDs may be read: ${JSON.stringify(sessionReads)}`);
    assert.deepEqual(pageErrors, [], "restore and Reader paths should have no browser errors");
    console.log("PASS side effects/errors: no search/session/turn POST; 0 page errors");

    const createdSessionId = "ui004-created-session";
    let createIntercepted = false;
    let turnIntercepted = false;
    await page.route("**/api/v1/chat/sessions", async (route) => {
      createIntercepted = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: { id: createdSessionId } }),
      });
    });
    await page.route(`**/api/v1/chat/sessions/${createdSessionId}/turns`, async (route) => {
      turnIntercepted = true;
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: 'event: delta\ndata: {"sequence":0,"text":"合成流式回答"}\n\nevent: done\ndata: {"saved":true}\n\n',
      });
    });
    await page.goto(`${targetUrl}${learnPath}?view=keep`);
    await page.getByLabel("围绕课程资料提问").fill("合成问题");
    await page.getByRole("button", { name: "发送问题" }).click();
    await page.waitForFunction((id) => new URL(window.location.href).searchParams.get("session_id") === id, createdSessionId);
    await page.getByText("合成流式回答", { exact: true }).waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await page.locator(".learn-turn").count(), 2, "URL state update must not clear the in-flight student/tutor turns");
    assert.equal(new URL(page.url()).searchParams.get("view"), "keep", "new session URL update must retain other query params");
    assert.ok(createIntercepted && turnIntercepted, "mocked session creation and SSE turn should run without backend writes");
    assert.ok(!sessionReads.includes(createdSessionId), "replaceState after creation must not trigger a redundant restore GET");
    console.log("PASS created-session URL: replaceState preserves query and does not clear the in-flight turn or trigger restore GET");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
