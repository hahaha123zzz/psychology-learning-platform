/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI008_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI008_STUDENT_EMAIL;
const password = process.env.UI008_STUDENT_PASSWORD;
const sessionId = process.env.UI008_SESSION_ID;
const courseTitle = "实验心理学｜学生端合成演示";
const browserPath = process.env.UI008_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password || !sessionId) {
  throw new Error("请提供 synthetic 学生账号和现有 course_qa session ID；本脚本不会启动服务、seed 数据或创建会话。");
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 20 });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const writes = [];
  const pageErrors = [];
  const searchResults = [];
  let sessionReads = 0;
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    page.on("request", (request) => {
      if (request.method() === "GET") return;
      const url = new URL(request.url());
      writes.push({ method: request.method(), path: url.pathname });
    });
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (url.pathname === `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`
        && response.request().method() === "GET") sessionReads += 1;
      if (url.pathname === "/api/v1/knowledge/search" && response.request().method() === "POST") {
        try {
          const envelope = await response.json();
          if (response.ok() && Array.isArray(envelope?.data?.items)) searchResults.push(...envelope.data.items);
        } catch { /* The Learn page renders its own API error state. */ }
      }
    });

    const courses = await page.evaluate(async () => {
      const response = await fetch("/api/v1/courses", { credentials: "include" });
      return { status: response.status, body: await response.json() };
    });
    assert.equal(courses.status, 200, "course list must come from the assigned API");
    const course = courses.body.data.find((item) => item.title === courseTitle);
    assert.ok(course, "the existing synthetic course must be present");

    const session = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/chat/sessions/${encodeURIComponent(id)}`, { credentials: "include" });
      return { status: response.status, body: await response.json() };
    }, sessionId);
    assert.equal(session.status, 200, "the supplied active session must be readable");
    assert.equal(session.body.data.id, sessionId);
    assert.equal(session.body.data.course_id, course.id);
    assert.equal(session.body.data.mode, "course_qa");
    assert.equal(session.body.data.status, "active");

    const invalidPointer = await page.evaluate(async () => {
      const response = await fetch("/api/v1/evidence-pointers/00000000000000000000000000", { credentials: "include" });
      return { status: response.status, body: await response.json() };
    });
    assert.equal(invalidPointer.status, 404, "an unknown pointer must fail closed as not found");
    assert.equal(invalidPointer.body.data, undefined);

    await page.goto(`${webOrigin}/student/courses/${course.id}/learn?session_id=${encodeURIComponent(sessionId)}`);
    await page.waitForFunction(() => {
      const composer = document.querySelector('input[aria-label="围绕课程资料提问"]');
      return composer instanceof HTMLInputElement && !composer.disabled;
    }, null, { timeout: 20_000 });
    assert.ok(sessionReads >= 2, "route restore must read the existing session again");
    const initialTableExplainCount = await page.locator(".table-explain-label").count();
    const initialTurnCount = await page.locator(".learn-turn").count();

    await page.getByLabel("搜索课程资料").fill("measure score recall");
    await page.getByLabel("只看表格").check();
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.locator(".evidence-list article").filter({ hasText: "表格对象" }).first().waitFor({ state: "visible", timeout: 20_000 });
    const figure = searchResults
      .flatMap((item) => Array.isArray(item.closure) ? item.closure : [])
      .find((item) => item.object_type === "figure" && typeof item.evidence_pointer_id === "string");
    assert.ok(figure, "the seeded synthetic table closure must include its Figure pointer");
    await page.getByText(/阅读顺序相邻图像 · 仅定位，图像语义暂不可解释/).waitFor({ state: "visible" });

    const pointerResponse = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/evidence-pointers/${encodeURIComponent(id)}`, { credentials: "include" });
      return { status: response.status, body: await response.json() };
    }, figure.evidence_pointer_id);
    assert.equal(pointerResponse.status, 200);
    const figurePointer = pointerResponse.body.data;
    assert.equal(figurePointer.evidence_pointer_id, figure.evidence_pointer_id);
    assert.equal(figurePointer.course_id, course.id);
    assert.equal(figurePointer.object_type, "figure");
    assert.equal(typeof figurePointer.excerpt, "string");
    assert.equal(figurePointer.excerpt.trim(), "", "the synthetic Figure has no extracted semantic text");

    const readerResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === `/api/v1/evidence-pointers/${encodeURIComponent(figure.evidence_pointer_id)}`
        && response.request().method() === "GET";
    });
    await page.getByRole("button", { name: "定位相邻图像", exact: true }).first().click();
    const readerResponse = await readerResponsePromise;
    assert.equal(readerResponse.status(), 200, "the selected Figure pointer must be reauthorized by Reader");
    const openedFigure = (await readerResponse.json()).data;
    assert.equal(openedFigure.evidence_pointer_id, figure.evidence_pointer_id);
    assert.equal(openedFigure.course_id, course.id);
    assert.equal(openedFigure.object_type, "figure");
    assert.equal(openedFigure.excerpt.trim(), "");
    const reader = page.getByRole("dialog", { name: "资料来源" });
    await reader.waitFor({ state: "visible", timeout: 20_000 });
    await reader.getByText("该对象只保存了图像位置；系统未解析图像含义。", { exact: true }).waitFor({ state: "visible" });
    await reader.getByText("图像语义尚未解析；当前只能定位，不能据此解释图像内容。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await reader.getByRole("button", { name: "向 Tutor 提问", exact: true }).count(), 0,
      "an empty Figure pointer must not offer a semantic Tutor action");
    assert.equal(await reader.getByText(/结论|表示了|说明了/).count(), 0,
      "Reader must not invent an image interpretation");
    await page.waitForFunction(() => {
      const pageImage = document.querySelector(".reader-image-viewport img[alt*='红框标出引用位置']");
      const fallback = document.querySelector(".evidence-pointer-limitation")?.textContent ?? "";
      return pageImage || fallback.includes("固定页图暂不可用") || fallback.includes("没有可验证的物理页");
    }, null, { timeout: 20_000 });
    const hasPageImage = await reader.locator(".reader-image-viewport img[alt*='红框标出引用位置']").count() > 0;
    const hasLocationFallback = await reader.getByText(/暂无可验证的物理页和 PDF 页内坐标|固定页图暂不可用/).count() > 0;
    assert.ok(hasPageImage || hasLocationFallback, "Figure view must show a verified page image or an explicit location fallback");
    await reader.getByRole("button", { name: "关闭上下文面板", exact: true }).click();

    assert.equal(await page.locator(".table-explain-label").count(), initialTableExplainCount,
      "opening a Figure Reader must not add a TableExplain label");
    assert.equal(await page.locator(".learn-turn").count(), initialTurnCount,
      "Figure location inspection must not create a Tutor turn");
    const tutorTurns = writes.filter((item) => item.path.endsWith("/turns"));
    assert.equal(tutorTurns.length, 0, "this Figure safety script does not send any Tutor turn");
    assert.equal(writes.filter((item) => item.path === "/api/v1/chat/sessions").length, 0,
      "the supplied session must be reused without creating another");
    assert.deepEqual(writes.map((item) => item.path), ["/api/v1/knowledge/search"],
      "table search is the only POST and is read-only");
    assert.deepEqual(pageErrors, [], "Learn and Reader should not raise client errors");
    console.log(`PASS UI-008 Figure safety: pointer=${figure.evidence_pointer_id}; unresolved semantics; zero Tutor turns`);
  } finally {
    assert.equal(writes.filter((item) => item.path.endsWith("/turns")).length, 0,
      "cleanup must not issue a Tutor turn");
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
