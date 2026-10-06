/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI007_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI007_STUDENT_EMAIL;
const password = process.env.UI007_STUDENT_PASSWORD;
const sessionId = process.env.UI007_SESSION_ID;
const courseTitle = "实验心理学｜学生端合成演示";
const browserPath = process.env.UI007_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password || !sessionId) {
  throw new Error("请通过环境变量提供隔离 synthetic 学生账号及现有 course_qa session；本脚本不会启动服务、seed 数据或创建会话。");
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 20 });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const writes = [];
  const pointerReads = [];
  const turnBodies = [];
  let sessionReads = 0;
  const pageErrors = [];
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
      const body = request.postDataJSON?.() ?? null;
      writes.push({ method: request.method(), path: url.pathname, body });
      if (url.pathname.endsWith("/turns")) turnBodies.push(body);
    });
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (url.pathname === `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`
        && response.request().method() === "GET") sessionReads += 1;
      if (url.pathname.startsWith("/api/v1/evidence-pointers/") && !url.pathname.endsWith("/page-image")) {
        try {
          const envelope = await response.json();
          if (envelope?.data?.evidence_pointer_id) pointerReads.push(envelope.data);
        } catch { /* Ignore non-JSON responses; the UI shows its own Reader error. */ }
      }
      if (url.pathname.endsWith("/turns") && response.request().method() === "POST" && response.status() >= 400) {
        throw new Error(`Tutor turn failed: HTTP ${response.status()}`);
      }
    });

    const courses = await page.evaluate(async () => {
      const response = await fetch("/api/v1/courses", { credentials: "include" });
      return { status: response.status, body: await response.json() };
    });
    assert.equal(courses.status, 200, "course list must come from the assigned API");
    const course = courses.body.data.find((item) => item.title === courseTitle);
    assert.ok(course, "the isolated synthetic course must already exist");

    const session = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/chat/sessions/${encodeURIComponent(id)}`, { credentials: "include" });
      return { status: response.status, body: await response.json() };
    }, sessionId);
    assert.equal(session.status, 200, "existing synthetic session must be readable");
    assert.equal(session.body.data.id, sessionId);
    assert.equal(session.body.data.course_id, course.id, "session must belong to the synthetic route course");
    assert.equal(session.body.data.mode, "course_qa", "only an existing active course_qa session is accepted");

    await page.goto(`${webOrigin}/student/courses/${course.id}/learn?session_id=${encodeURIComponent(sessionId)}`);
    await page.waitForFunction(() => {
      const composer = document.querySelector('input[aria-label="围绕教材提问"]');
      return composer instanceof HTMLInputElement && !composer.disabled;
    }, null, { timeout: 20_000 });
    assert.ok(sessionReads >= 2, "the preflight and Learn route must both GET the explicit session");
    await page.getByLabel("搜索教材").fill("measure score recall");
    await page.getByLabel("只看表格").check();
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    const tableCard = page.locator(".evidence-list article").filter({ hasText: "表格对象" }).first();
    await tableCard.waitFor({ state: "visible", timeout: 20_000 });
    await tableCard.getByRole("button", { name: "查看表格固定来源", exact: true }).click();
    const reader = page.getByRole("dialog", { name: "教材来源快照" });
    await reader.waitFor({ state: "visible", timeout: 20_000 });
    await reader.getByRole("button", { name: "向 Tutor 提问", exact: true }).click();
    await page.getByText("待解释的表格", { exact: true }).waitFor({ state: "visible" });

    const question = "请解释这张表格的主要信息。";
    await page.getByLabel("围绕教材提问").fill(question);
    await page.getByRole("button", { name: "发送问题" }).click();
    await page.getByText("表格解释 · 来自已核验的表格引用", { exact: true }).waitFor({ state: "visible", timeout: 60_000 });
    assert.equal(turnBodies.length, 1, "exactly one synthetic Tutor turn may be sent");
    assert.equal(pointerReads.length >= 2, true, "Reader and Learn must reload pointer metadata from the server");
    const selectedPointerId = pointerReads.find((item) => item.object_type === "table" && item.excerpt?.trim())?.evidence_pointer_id;
    assert.ok(selectedPointerId, "selected pointer must be an authorized non-empty native table");

    const turnBody = turnBodies[0];
    assert.deepEqual(Object.keys(turnBody).sort(), ["client_turn_id", "content", "selected_evidence_pointer_ids"].sort());
    assert.equal(turnBody.content, question);
    assert.deepEqual(turnBody.selected_evidence_pointer_ids, [selectedPointerId]);
    assert.equal(JSON.stringify(turnBody).includes("Measure | Score"), false, "client must not send table excerpts");
    assert.equal(writes.filter((item) => item.path.endsWith("/turns")).length, 1);
    const persistedWrites = writes.filter((item) => item.path !== "/api/v1/knowledge/search");
    assert.equal(persistedWrites.filter((item) => item.path === "/api/v1/chat/sessions").length, 0, "the browser must reuse the existing session");
    assert.equal(persistedWrites.filter((item) => item.path.endsWith("/turns")).length, 1);
    assert.equal(persistedWrites.every((item) => item.path.endsWith("/turns")), true);
    assert.equal(writes.filter((item) => item.path === "/api/v1/knowledge/search").length, 1,
      "the sole extra POST is read-only table search");

    const citationButton = page.getByRole("button", { name: "打开引用", exact: true }).last();
    await citationButton.waitFor({ state: "visible", timeout: 20_000 });
    await citationButton.click();
    const citationReader = page.getByRole("dialog", { name: "教材来源快照" });
    await citationReader.waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(pointerReads.at(-1)?.evidence_pointer_id, selectedPointerId, "the citation must reopen the exact selected table pointer");
    const citationVersion = pointerReads.find((item) => item.evidence_pointer_id === selectedPointerId)?.material_version_id;
    assert.ok(citationVersion);
    await citationReader.getByText(citationVersion, { exact: true }).waitFor({ state: "visible" });
    assert.deepEqual(pageErrors, [], "Learn/Reader should not raise client errors");
    console.log(`PASS UI-007 TableExplain→Citation→Reader: one pointer-only Tutor turn, pointer=${selectedPointerId}`);
  } finally {
    const tutorTurns = writes.filter((item) => item.path.endsWith("/turns"));
    assert.ok(tutorTurns.length <= 1, "cleanup must never send a second Tutor turn");
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
