/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const baseUrl = process.env.UI011_BASE_URL ?? "http://127.0.0.1:3001";
const email = process.env.UI011_EMAIL;
const password = process.env.UI011_PASSWORD;
const expectedTaskId = process.env.UI011_TASK_ID;
const browserPath = process.env.UI011_BROWSER;

if (!email || !password || !expectedTaskId) {
  throw new Error("请设置 UI011_EMAIL、UI011_PASSWORD、UI011_TASK_ID，使用现有 synthetic 任务；脚本不会创建任务或提交回答。");
}

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const pageErrors = [];
  const businessWrites = [];
  const taskRestores = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${baseUrl}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    // 在登录完成后开始记录；本脚本只允许读取和页面导航，不触发业务写。
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/v1/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        businessWrites.push(`${request.method()} ${url.pathname}`);
      }
    });
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (url.pathname === `/api/v1/student/learning/tasks/${expectedTaskId}` && response.request().method() === "GET") {
        try {
          const envelope = await response.json();
          taskRestores.push({ status: response.status(), task: envelope.data });
        } catch {
          taskRestores.push({ status: response.status(), task: null });
        }
      }
    });

    await page.goto(`${baseUrl}/student`);
    await page.getByRole("heading", { name: "继续你的学习" }).waitFor({ state: "visible" });
    const home = await page.evaluate(async () => {
      const response = await fetch("/api/v1/student/home");
      const envelope = await response.json();
      if (!response.ok) throw new Error(`Home GET failed: ${response.status}`);
      return envelope.data;
    });
    const current = home.current_task;
    assert.ok(current, "synthetic Home projection must already have a current task");
    assert.equal(current.task_id ?? current.id, expectedTaskId, "Home current task must match the supplied synthetic task");
    const expectedCourseId = current.course_id;
    assert.ok(expectedCourseId, "Home current task must have an authorized course id");

    const resume = page.getByRole("link", { name: /继续当前任务|恢复当前任务/ });
    await resume.waitFor({ state: "visible" });
    await resume.click();
    await page.waitForURL((url) => url.pathname === "/student/learning", { timeout: 20_000 });
    assert.equal(await page.evaluate(() => sessionStorage.getItem("student-learning-task")), expectedTaskId);
    await page.getByRole("heading", { name: "AI 引导学习" }).waitFor({ state: "visible" });
    await page.waitForFunction((id) => sessionStorage.getItem("student-learning-task") === id, expectedTaskId);
    await page.getByText(/当前阶段：/).waitFor({ state: "visible" });

    const firstRestore = taskRestores.at(-1);
    assert.equal(firstRestore?.status, 200, "guided task restore GET should succeed");
    assert.equal(firstRestore.task.id, expectedTaskId);
    assert.equal(firstRestore.task.course_id, expectedCourseId);
    const expectedState = firstRestore.task.state;
    const expectedVersion = firstRestore.task.state_version;

    const courseLearn = page.getByRole("link", { name: "打开课程教材与学习助手", exact: true });
    await courseLearn.waitFor({ state: "visible" });
    await courseLearn.click();
    await page.waitForURL((url) => url.pathname === `/student/courses/${encodeURIComponent(expectedCourseId)}/learn`, { timeout: 20_000 });
    await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
    assert.equal(new URL(page.url()).search, "", "task/content must not be copied into query parameters");
    assert.equal(await page.evaluate(() => sessionStorage.getItem("student-learning-task")), expectedTaskId, "course Learn navigation must preserve current task recovery");

    await page.getByRole("link", { name: "返回引导学习任务", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/student/learning", { timeout: 20_000 });
    await page.getByText(/当前阶段：/).waitFor({ state: "visible" });
    assert.equal(await page.evaluate(() => sessionStorage.getItem("student-learning-task")), expectedTaskId);
    assert.ok(taskRestores.length >= 2, "return navigation should re-read the exact saved task");
    const finalRestore = taskRestores.at(-1);
    assert.equal(finalRestore.status, 200);
    assert.equal(finalRestore.task.id, expectedTaskId);
    assert.equal(finalRestore.task.course_id, expectedCourseId);
    assert.equal(finalRestore.task.state, expectedState);
    assert.equal(finalRestore.task.state_version, expectedVersion);

    assert.deepEqual(businessWrites, [], "登录后的 Home/task/Learn navigation must have zero business writes");
    assert.deepEqual(pageErrors, [], "Home/task/Learn navigation must have no browser errors");
    console.log(`PASS UI-011: task ${expectedTaskId} course ${expectedCourseId} survives Home→guided task→course Learn→guided task; state=${expectedState}, version=${expectedVersion}; zero post-login business writes`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
