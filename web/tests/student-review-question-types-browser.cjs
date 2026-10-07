/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI031_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI031_STUDENT_EMAIL;
const password = process.env.UI031_STUDENT_PASSWORD;
const courseId = process.env.UI031_COURSE_ID;
const browserPath = process.env.UI031_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password || !courseId) {
  throw new Error("请提供本地合成学生账号和课程 ID；本脚本只 mock Review API，不启动或 seed 服务。");
}

const dueAt = new Date(Date.now() - 60_000).toISOString();
const questionOptions = [
  { key: "A", text: "合成选项 A" },
  { key: "B", text: "合成选项 B" },
  { key: "C", text: "合成选项 C" },
];
const reviews = [
  { id: "01J00000000000000000000001", course_id: courseId, reason: "wrong_answer", due_at: dueAt, version: 3, question: { type: "single", stem: "合成单选复习题", options: questionOptions.slice(0, 2) } },
  { id: "01J00000000000000000000002", course_id: courseId, reason: "wrong_answer", due_at: dueAt, version: 4, question: { type: "multiple", stem: "合成多选复习题", options: questionOptions } },
  { id: "01J00000000000000000000003", course_id: courseId, reason: "wrong_answer", due_at: dueAt, version: 5, question: { type: "true_false", stem: "合成判断复习题", options: [] } },
  { id: "01J00000000000000000000004", course_id: courseId, reason: "wrong_answer", due_at: dueAt, version: 6, question: { type: "essay", stem: "合成主观复习题", options: [] } },
];

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  const writes = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    await page.route(`**/api/v1/courses/${courseId}/assessments`, (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], meta: { request_id: "ui031-assessments", server_time: new Date().toISOString() } }),
    }));
    await page.route(/\/api\/v1\/review-tasks\?due_only=false$/, (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: reviews, meta: { request_id: "ui031-reviews", server_time: new Date().toISOString() } }),
    }));
    await page.route(/\/api\/v1\/review-tasks\/[^/]+\/(verify|complete)$/, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const taskId = url.pathname.split("/").at(-2);
      let body = null;
      try { body = request.postDataJSON(); } catch { /* close-without-answer must have no JSON body */ }
      writes.push({ method: request.method(), taskId, action: url.pathname.endsWith("/verify") ? "verify" : "complete", body });
      if (url.pathname.endsWith("/verify")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ data: { id: taskId, status: "done", event_id: `event-${taskId}`, pending_qualification: false }, meta: { request_id: "ui031-verify", server_time: new Date().toISOString() } }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: { id: taskId, status: "done" }, meta: { request_id: "ui031-close", server_time: new Date().toISOString() } }),
      });
    });

    await page.goto(`${webOrigin}/student/courses/${courseId}/practice`);
    await page.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
    const singleRow = page.locator('[data-review-task-id="01J00000000000000000000001"]');
    await singleRow.getByRole("combobox", { name: "选择复习答案" }).selectOption("B");
    await singleRow.getByText(/可复习时间：/).waitFor({ state: "visible" });
    await singleRow.getByRole("button", { name: "验证并完成", exact: true }).click();
    await singleRow.waitFor({ state: "detached" });

    const multipleRow = page.locator('[data-review-task-id="01J00000000000000000000002"]');
    await multipleRow.getByRole("checkbox", { name: "A. 合成选项 A" }).check();
    await multipleRow.getByRole("checkbox", { name: "C. 合成选项 C" }).check();
    await multipleRow.getByRole("button", { name: "验证并完成", exact: true }).click();
    await multipleRow.waitFor({ state: "detached" });

    const trueFalseRow = page.locator('[data-review-task-id="01J00000000000000000000003"]');
    await trueFalseRow.getByRole("radio", { name: "否" }).check();
    await trueFalseRow.getByRole("button", { name: "验证并完成", exact: true }).click();
    await trueFalseRow.waitFor({ state: "detached" });

    const subjectiveRow = page.locator('[data-review-task-id="01J00000000000000000000004"]');
    await subjectiveRow.getByText("此复习题型不支持答案验证").waitFor({ state: "visible" });
    assert.equal(await subjectiveRow.getByRole("button", { name: "验证并完成", exact: true }).count(), 0);
    assert.equal(await subjectiveRow.getByRole("textbox").count(), 0, "主观题关闭路径不得收集答案");
    await subjectiveRow.getByRole("button", { name: "关闭复习任务（不提交答案）", exact: true }).click();
    await subjectiveRow.waitFor({ state: "detached" });

    assert.deepEqual(writes, [
      { method: "POST", taskId: reviews[0].id, action: "verify", body: { version: 3, response: { selected_keys: ["B"] } } },
      { method: "POST", taskId: reviews[1].id, action: "verify", body: { version: 4, response: { selected_keys: ["A", "C"] } } },
      { method: "POST", taskId: reviews[2].id, action: "verify", body: { version: 5, response: { selected_keys: false } } },
      { method: "POST", taskId: reviews[3].id, action: "complete", body: null },
    ], "答案形状必须按原题型提交；主观题关闭不得提交答案或 evidence");
    assert.deepEqual(pageErrors, []);
    console.log(JSON.stringify({ verified_types: ["single", "multiple", "true_false"], subjective_closed_without_answer: true, writes: writes.length, page_errors: pageErrors.length }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
