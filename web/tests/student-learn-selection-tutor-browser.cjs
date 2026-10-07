/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const origin = process.env.UI034_APP_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI034_STUDENT_EMAIL;
const password = process.env.UI034_STUDENT_PASSWORD;
const executablePath = process.env.UI034_CHROME_PATH;
const courseId = "01M00000000000000000000301";
const otherCourseId = "01M00000000000000000000302";
const sessionId = "01M00000000000000000000303";
const otherSessionId = "01M00000000000000000000304";
const pointerId = "01M00000000000000000000305";
const storageKey = "student-learn-selection-context";
const envelope = (data) => ({ data, meta: { request_id: "ui034-mock", server_time: "2026-10-07T00:00:00Z" } });

async function main() {
  if (!email || !password) throw new Error("Set UI034_STUDENT_EMAIL and UI034_STUDENT_PASSWORD to synthetic local credentials.");
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const turnBodies = [];
  const learningEventBodies = [];
  let restoreTurns = [];
  let citationEvent;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/v1/auth/login" && method === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ display_name: "Synthetic learner", platform_roles: [] })) });
    } else if ((path === `/api/v1/courses/${courseId}/materials` || path === `/api/v1/courses/${otherCourseId}/materials`) && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([{ id: "synthetic-material", title: "Synthetic course material", current_version: { id: "synthetic-version", version_no: 1, status: "published" } }])) });
    } else if (path === "/api/v1/student/intervention-runs" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if ((path === `/api/v1/chat/sessions/${sessionId}` || path === `/api/v1/chat/sessions/${otherSessionId}`) && method === "GET") {
      const currentCourse = path.endsWith(sessionId) ? courseId : otherCourseId;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        id: path.endsWith(sessionId) ? sessionId : otherSessionId,
        course_id: currentCourse,
        mode: "course_qa",
        turns: currentCourse === courseId ? restoreTurns : [],
      })) });
    } else if (path === "/api/v1/knowledge/search" && method === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ items: [{
        title: "Synthetic paragraph",
        text: "Synthetic search result only.",
        object_type: "paragraph",
        material_type: "other",
        evidence_id: "synthetic-evidence",
        evidence_pointer_id: pointerId,
      }] })) });
    } else if (path === `/api/v1/evidence-pointers/${pointerId}` && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        evidence_pointer_id: pointerId,
        course_id: courseId,
        material_title: "Synthetic course material",
        material_id: "synthetic-material",
        material_version_id: "synthetic-version",
        publication_snapshot_id: "synthetic-snapshot",
        index_job_id: "synthetic-index",
        domain_release_id: "synthetic-domain",
        chapter_path: "Synthetic chapter",
        physical_page: 1,
        object_type: "paragraph",
        coordinate_space: "unavailable",
        bbox: null,
        anchors: [],
        excerpt: "Synthetic pointer excerpt",
        excerpt_sha256: "synthetic-only",
      })) });
    } else if (path === "/api/v1/learning-events" && method === "POST") {
      learningEventBodies.push(request.postDataJSON());
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(envelope({ id: "synthetic-learning-event" })) });
    } else if (path === `/api/v1/chat/sessions/${sessionId}/turns` && method === "POST") {
      const body = request.postDataJSON();
      turnBodies.push(body);
      if (turnBodies.length === 1) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "SYNTHETIC_RETRY", message: "Synthetic temporary failure", details: {}, retryable: true }, request_id: "ui034-failed" }) });
      } else {
        citationEvent = { evidence_pointer_id: pointerId, label: "Synthetic selected pointer citation", material_type: "other" };
        const answer = "Synthetic local Tutor answer.";
        restoreTurns = [{ role: "tutor", content: answer, citations: [{ ...citationEvent }] }];
        const frames = [
          `event: delta\ndata: ${JSON.stringify({ text: answer })}`,
          `event: citation\ndata: ${JSON.stringify(citationEvent)}`,
          `event: done\ndata: ${JSON.stringify({ saved: true })}`,
        ].join("\n\n") + "\n\n";
        await route.fulfill({ status: 200, contentType: "text/event-stream", body: frames });
      }
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "UNEXPECTED_MOCK", message: `Unexpected synthetic route: ${method} ${path}` }, request_id: "ui034-unexpected" }) });
    }
  });

  try {
    await page.goto(`${origin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/student", { timeout: 15_000 });
    await page.goto(`${origin}/student/courses/${courseId}/learn?session_id=${sessionId}`);
    await page.getByLabel("搜索课程资料").fill("synthetic concept");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).waitFor({ state: "visible" });
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).click();
    const reader = page.getByRole("dialog", { name: "资料来源" });
    await reader.getByText("Synthetic pointer excerpt", { exact: true }).waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    const stored = await page.evaluate((key) => sessionStorage.getItem(key), storageKey);
    assert.equal(stored, JSON.stringify({ course_id: courseId, evidence_pointer_id: pointerId }));

    const question = "请解释这个合成段落。";
    const questionInput = page.getByRole("textbox", { name: "围绕课程资料提问" });
    await questionInput.fill(question);
    await questionInput.press("Enter");
    await page.getByText("Synthetic temporary failure", { exact: false }).waitFor({ state: "visible" });
    assert.equal(await questionInput.inputValue(), question, "temporary failure preserves the question");
    await questionInput.press("Enter");
    await page.getByText("Synthetic selected pointer citation", { exact: true }).waitFor({ state: "visible" });
    assert.equal(turnBodies.length, 2);
    for (const turnBody of turnBodies) {
      assert.deepEqual(Object.keys(turnBody).sort(), ["client_turn_id", "content", "selected_evidence_pointer_ids"]);
      assert.equal(turnBody.content, question);
      assert.deepEqual(turnBody.selected_evidence_pointer_ids, [pointerId]);
    }
    assert.equal(turnBodies[0].client_turn_id, turnBodies[1].client_turn_id, "retry uses the same pointer-bound idempotency key");
    assert.equal(citationEvent.evidence_pointer_id, pointerId, "returned citation is the exact selected pointer ID");
    assert.ok(learningEventBodies.length >= 1, "authorized Reader open may record the existing resource-open event");
    for (const eventBody of learningEventBodies) {
      assert.deepEqual(Object.keys(eventBody).sort(), ["course_id", "event_key", "evidence_pointer_id"]);
      assert.equal(eventBody.course_id, courseId);
      assert.equal(eventBody.evidence_pointer_id, pointerId);
    }
    const citationButton = page.getByRole("button", { name: "打开引用", exact: true });
    assert.equal(await citationButton.count(), 1, "the Tutor turn exposes its returned citation pointer");
    await citationButton.click();
    const citationReader = page.getByRole("dialog", { name: "资料来源" });
    await citationReader.getByText("Synthetic pointer excerpt", { exact: true }).waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await citationReader.waitFor({ state: "hidden" });

    await page.reload();
    await page.getByText("Synthetic selected pointer citation", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), stored, "Reader context survives refresh");
    await page.getByRole("button", { name: "清除选择", exact: true }).click();
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), null, "clear removes the pointer context");

    await page.getByLabel("搜索课程资料").fill("synthetic concept");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).click();
    await reader.waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    await page.goto(`${origin}/student/courses/${otherCourseId}/learn?session_id=${otherSessionId}`);
    await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), null, "course change clears the prior course pointer");
    console.log("PASS UI-034 synthetic mock browser: Reader pointer ID sent alone, retry binds same ID, exact citation, refresh persistence, clear/course cleanup");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
