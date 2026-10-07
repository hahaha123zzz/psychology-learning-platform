/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.REVIEW_WEB_ORIGIN ?? "http://127.0.0.1:3012";
const email = process.env.REVIEW_STUDENT_EMAIL;
const password = process.env.REVIEW_STUDENT_PASSWORD;
const questionStem = "【本地合成演示】研究者操纵的变量是什么？";
const browserPath = process.env.REVIEW_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password) throw new Error("需要指定已完成五题 Practice 的本地 synthetic 学生账号。");

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
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/v1/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        writes.push({ method: request.method(), path: url.pathname, body: request.postDataJSON?.() ?? null });
      }
    });
    const preflight = await page.evaluate(async (stem) => {
      const coursesResponse = await fetch("/api/v1/courses");
      const courses = await coursesResponse.json();
      const course = courses.data.find((item) => item.title === "实验心理学｜学生端合成演示");
      if (!course) throw new Error("未找到隔离合成课程");
      const reviewsResponse = await fetch("/api/v1/review-tasks?due_only=false");
      const reviews = await reviewsResponse.json();
      const pending = reviews.data.filter((item) => item.course_id === course.id
        && item.reason === "wrong_answer" && item.status === "pending" && item.question?.stem === stem);
      return { course, pending };
    }, questionStem);
    const task = preflight.pending.find((item) => Date.parse(item.due_at) <= Date.now());
    assert.ok(task, "must use an existing due wrong-answer review task from the synthetic attempt");
    assert.ok(task.question.options.some((option) => option.key === "A" && option.text === "自变量"),
      "the pinned synthetic question version must expose its known synthetic choice A");

    await page.goto(`${webOrigin}/student/courses/${preflight.course.id}/practice`);
    const row = page.locator(`[data-review-task-id="${task.id}"]`);
    await row.waitFor({ state: "visible", timeout: 20_000 });
    await row.getByRole("combobox", { name: "选择复习答案" }).selectOption("A");
    await row.getByRole("button", { name: "验证并完成", exact: true }).click();
    const success = page.getByRole("status").filter({ hasText: "复习答案已提交" });
    await success.waitFor({ state: "visible", timeout: 20_000 });
    await row.waitFor({ state: "detached", timeout: 20_000 });
    const remaining = await page.evaluate(async (id) => {
      const response = await fetch("/api/v1/review-tasks?due_only=false");
      const envelope = await response.json();
      return envelope.data.some((item) => item.id === id);
    }, task.id);
    assert.equal(remaining, false, "verified task must leave the pending Review projection");
    assert.equal(writes.length, 1, "review-only stage may perform one business write");
    assert.equal(writes[0].method, "POST");
    assert.equal(writes[0].path, `/api/v1/review-tasks/${task.id}/verify`);
    assert.deepEqual(writes[0].body.response.selected_keys, ["A"]);
    assert.deepEqual(pageErrors, []);
    console.log(`PASS Review completion: student=${email} task=${task.id} due=true correct=A; one verify write`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
