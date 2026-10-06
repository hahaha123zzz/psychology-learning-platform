/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI010_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI010_STUDENT_EMAIL;
const password = process.env.UI010_STUDENT_PASSWORD;
const browserPath = process.env.UI010_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password) {
  throw new Error("请通过 UI010_STUDENT_EMAIL / UI010_STUDENT_PASSWORD 提供 runbook synthetic 凭据；脚本不会启动服务或创建任务。");
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 10 });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const businessWrites = [];
  const restoreReads = [];
  const homeReads = [];
  const pageErrors = [];
  const apiErrors = [];
  const failedApiRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    const preflight = await page.evaluate(async () => {
      const [homeResponse, coursesResponse] = await Promise.all([
        fetch("/api/v1/student/home", { credentials: "include" }),
        fetch("/api/v1/courses", { credentials: "include" }),
      ]);
      const [home, courses] = await Promise.all([homeResponse.json(), coursesResponse.json()]);
      return { homeStatus: homeResponse.status, coursesStatus: coursesResponse.status, home: home.data, courses: courses.data };
    });
    assert.equal(preflight.homeStatus, 200, "read-only Home preflight should succeed");
    assert.equal(preflight.coursesStatus, 200, "read-only course preflight should succeed");
    const task = preflight.home?.current_task;
    assert.ok(task?.task_id, "the existing synthetic account must already have a current task");
    assert.equal(task.id, task.task_id, "Home task_id must point to the current LearningSession");
    assert.equal(task.status, "active", "the seeded task must expose the ‘继续当前任务’ CTA");
    assert.ok(task.course_id && task.state, "the Home task must expose its course and state");
    assert.ok(Number.isInteger(task.state_version), "the Home task must expose its server version");
    const course = preflight.courses.find((item) => item.id === task.course_id);
    assert.ok(course, "the task course must be in the authorized course list");
    const restorePath = `/api/v1/student/learning/tasks/${encodeURIComponent(task.task_id)}`;

    page.on("request", (request) => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith("/api/v1/")) return;
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        businessWrites.push({ method: request.method(), path: url.pathname });
      }
      if (url.pathname === restorePath && request.method() === "GET") {
        restoreReads.push({ method: request.method(), path: url.pathname });
      }
      if (url.pathname === "/api/v1/student/home" && request.method() === "GET") {
        homeReads.push({ method: request.method(), status: null });
      }
    });
    page.on("response", (response) => {
      const url = new URL(response.url());
      if (url.pathname.startsWith("/api/v1/") && response.status() >= 400) {
        apiErrors.push({ status: response.status(), path: url.pathname });
      }
      if (url.pathname === "/api/v1/student/home" && response.request().method() === "GET" && response.status() < 400) {
        const read = homeReads.find((item) => item.status === null);
        if (read) read.status = response.status();
      }
    });
    page.on("requestfailed", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/v1/")) {
        failedApiRequests.push({ path: url.pathname, error: request.failure()?.errorText ?? "unknown" });
      }
    });

    await page.evaluate(() => sessionStorage.removeItem("student-learning-task"));
    await page.goto(`${webOrigin}/student`);
    const continueLink = page.getByRole("link", { name: "继续当前任务", exact: true });
    await continueLink.waitFor({ state: "visible", timeout: 20_000 });
    const restoreResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === restorePath && response.request().method() === "GET";
    }, { timeout: 20_000 });
    await continueLink.click();
    await page.waitForURL((url) => url.pathname === "/student/learning", { timeout: 20_000 });
    assert.equal(await page.evaluate(() => sessionStorage.getItem("student-learning-task")), task.task_id);

    const response = await restoreResponsePromise;
    assert.equal(response.status(), 200, "the current task restore GET must succeed");
    const restored = (await response.json())?.data;
    assert.equal(restored?.id, task.id);
    assert.equal(restored?.task_id, task.task_id);
    assert.equal(restored?.course_id, task.course_id);
    assert.equal(restored?.state, task.state);
    assert.equal(restored?.state_version, task.state_version);
    assert.equal(restored?.status, task.status);

    const activeNavLabels = await page.locator(".functional-nav .data-nav.active").allInnerTexts();
    assert.ok(activeNavLabels.some((label) => label.trim() === course.title),
      "the restored view must select the same course");
    await page.getByText(`当前阶段：${task.state}`, { exact: true }).waitFor({ state: "visible", timeout: 20_000 });
    assert.ok(restoreReads.length >= 1 && restoreReads.every((item) => item.path === restorePath && item.method === "GET"));
    assert.deepEqual(businessWrites, [], "the flow must issue no business writes");
    assert.deepEqual(apiErrors, [], "the flow must have no API errors");
    assert.ok(failedApiRequests.every((item) =>
      item.path === "/api/v1/student/home" && item.error === "net::ERR_ABORTED"),
    "only a duplicate Home GET cancelled by navigation may fail");
    assert.ok(homeReads.some((item) => item.status === 200), "the rendered Home route must have a successful Home GET");
    assert.deepEqual(pageErrors, [], "the flow must have no page errors");

    console.log(JSON.stringify({ result: "PASS", task_id: task.task_id, course_id: task.course_id,
      state: task.state, state_version: task.state_version, restore_path: restorePath,
      restore_reads: restoreReads.length, home_reads: homeReads, failed_api_requests: failedApiRequests,
      business_writes: 0, api_errors: 0, page_errors: 0 }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
