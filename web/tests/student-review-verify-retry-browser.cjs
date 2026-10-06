/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const appOrigin = process.env.UI026_WEB_ORIGIN ?? "http://127.0.0.1:3217";
const browserPath = process.env.UI026_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";
const courseId = "synthetic-course-ui026";
const reviewId = "synthetic-review-ui026";
const eventId = "synthetic-event-ui026";
const review = {
  id: reviewId,
  course_id: courseId,
  reason: "wrong_answer",
  due_at: "2020-01-01T00:00:00Z",
  version: 7,
  status: "pending",
  question: {
    type: "single",
    stem: "本地合成复习：哪项是自变量？",
    options: [{ key: "A", text: "研究者操纵的因素" }, { key: "B", text: "研究者测量的结果" }],
  },
};
const writes = [];
const unexpectedRequests = [];
let verifyCalls = 0;

const envelope = (data) => ({ data, meta: { request_id: "synthetic-ui026", server_time: "2026-10-06T00:00:00Z" } });
const respond = (route, status, body) => route.fulfill({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let body = null;
    try { body = request.postDataJSON(); } catch { /* 无 JSON body 的请求仍按写请求计数。 */ }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) writes.push({ method, path, body });

    if (method === "GET" && path === "/api/v1/me") {
      return respond(route, 200, envelope({ id: "synthetic-user-ui026", platform_roles: ["student"] }));
    }
    if (method === "GET" && path === "/api/v1/courses") {
      return respond(route, 200, envelope([{ id: courseId, title: "本地合成课程" }]));
    }
    if (method === "GET" && path === `/api/v1/courses/${courseId}/assessments`) {
      return respond(route, 200, envelope([]));
    }
    if (method === "GET" && path === "/api/v1/review-tasks") {
      return respond(route, 200, envelope([review]));
    }
    if (method === "GET" && path === "/api/v1/student/labs/catalog") {
      return respond(route, 200, envelope([]));
    }
    if (method === "GET" && path === "/api/v1/student/labs/active") {
      return respond(route, 200, envelope(null));
    }
    if (method === "POST" && path === `/api/v1/review-tasks/${reviewId}/verify`) {
      verifyCalls += 1;
      if (verifyCalls === 1) {
        return respond(route, 503, { error: { code: "SYNTHETIC_RETRYABLE_FAILURE", message: "合成验证暂时失败，请保留答案后重试。", retryable: true } });
      }
      if (verifyCalls === 2) {
        return respond(route, 200, envelope({ event_id: eventId, pending_qualification: true }));
      }
    }
    if (method === "GET" && path === "/api/v1/me/learning-events") {
      return respond(route, 200, envelope([{
        id: eventId,
        course_id: courseId,
        qualification_status: "qualified",
      }]));
    }

    unexpectedRequests.push(`${method} ${path}`);
    return respond(route, 404, { error: { code: "MOCK_ROUTE_NOT_ALLOWED", message: "此 UI-026 mock route 未开放。" } });
  });

  try {
    await page.goto(`${appOrigin}/student/courses/${courseId}/practice`);
    await page.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
    const row = page.locator(`[data-review-task-id="${reviewId}"]`);
    await row.waitFor({ state: "visible" });

    const answer = row.getByRole("combobox", { name: "选择复习答案" });
    const verify = row.getByRole("button", { name: "验证并完成", exact: true });
    await answer.selectOption("A");
    await verify.click();

    const failure = page.getByRole("status").filter({ hasText: "合成验证暂时失败，请保留答案后重试。" });
    await failure.waitFor({ state: "visible" });
    assert.equal(await row.isVisible(), true, "verify 首次失败后任务卡必须保留");
    assert.equal(await answer.inputValue(), "A", "verify 首次失败后所选答案必须保留");
    assert.equal(await verify.isEnabled(), true, "失败后应允许用户重试");
    assert.equal(await failure.getAttribute("aria-live"), "polite", "失败消息应处于可访问 live region");

    await verify.click();
    await row.waitFor({ state: "detached" });
    await page.getByRole("status").filter({ hasText: "复习记录已通过资格确认" }).waitFor({ state: "visible" });

    assert.equal(verifyCalls, 2, "一次失败后只允许一次显式重试成功");
    assert.deepEqual(writes, [
      { method: "POST", path: `/api/v1/review-tasks/${reviewId}/verify`, body: { version: 7, response: { selected_keys: ["A"] } } },
      { method: "POST", path: `/api/v1/review-tasks/${reviewId}/verify`, body: { version: 7, response: { selected_keys: ["A"] } } },
    ], "两次验证都必须提交同一合成任务与保留的所选答案");
    assert.deepEqual(unexpectedRequests, [], "mock 浏览器不得触发未声明的 API 请求");
    assert.deepEqual(pageErrors, [], "Review mock browser should not produce page errors");
    console.log(JSON.stringify({
      mock_only: true,
      first_verify_failed: true,
      pending_task_and_answer_retained: true,
      accessible_retry_message: true,
      retry_succeeded_and_task_removed: true,
      qualification_state_announced: "qualified",
      verify_writes: writes.length,
      page_errors: pageErrors.length,
    }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
