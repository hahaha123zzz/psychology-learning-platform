// R3-E 独立浏览器回归：学生提交后结果保持隐藏，教师手动发布后学生可重开结果。
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webOrigin = process.env.R3_E_WEB_ORIGIN ?? "http://127.0.0.1:3214";
const devtoolsOrigin = process.env.R3_E_CDP_ORIGIN ?? "http://127.0.0.1:9314";
const teacherEmail = process.env.R3_E_TEACHER_EMAIL;
const studentEmail = process.env.R3_E_STUDENT_EMAIL;
const password = process.env.R3_E_E2E_PASSWORD ?? "r3-e-local-only-password";
assert.ok(teacherEmail && studentEmail, "缺少 R3-E 隔离浏览器账号环境变量");

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class DevToolsPage {
  #socket;
  #nextId = 0;
  #pending = new Map();
  #opened;

  constructor(url) {
    this.#socket = new WebSocket(url);
    this.#opened = new Promise((resolve, reject) => {
      this.#socket.addEventListener("open", resolve, { once: true });
      this.#socket.addEventListener("error", reject, { once: true });
    });
    this.#socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      const pending = this.#pending.get(message.id);
      if (!pending) return;
      this.#pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result ?? {});
    });
    this.#socket.addEventListener("close", () => {
      for (const pending of this.#pending.values()) {
        pending.reject(new Error("R3-E 隔离浏览器 CDP 连接已关闭"));
      }
      this.#pending.clear();
    });
  }

  async send(method, params = {}) {
    await this.#opened;
    const id = ++this.#nextId;
    return new Promise((resolve, reject) => {
      this.#pending.set(id, { resolve, reject });
      this.#socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const response = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.text ?? "浏览器脚本执行失败");
    }
    return response.result?.value;
  }

  close() {
    this.#socket.close();
  }
}

async function waitFor(page, expression, label, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await page.evaluate(expression);
    if (value) return value;
    await pause(200);
  }
  throw new Error(`等待浏览器状态超时：${label}`);
}

async function api(page, path, { method = "GET", body } = {}) {
  const expression = `(async () => {
    const response = await fetch('/api/v1' + ${JSON.stringify(path)}, {
      method: ${JSON.stringify(method)}, credentials: 'include',
      headers: ${body === undefined ? "{}" : "{'content-type':'application/json'}"},
      ${body === undefined ? "" : `body: JSON.stringify(${JSON.stringify(body)}),`}
    });
    return {status: response.status, body: await response.json()};
  })()`;
  return page.evaluate(expression);
}

async function login(page, email) {
  const result = await api(page, "/auth/login", {
    method: "POST",
    body: { email, password },
  });
  assert.equal(result.status, 200, `隔离浏览器登录失败：HTTP ${result.status}`);
}

async function main() {
  const assessmentPageUrl = `${webOrigin}/student/assessments`;
  const created = await fetch(`${devtoolsOrigin}/json/new?${encodeURIComponent(assessmentPageUrl)}`, {
    method: "PUT",
  });
  assert.ok(created.ok, `Chromium 新建标签失败：HTTP ${created.status}`);
  const target = await created.json();
  const page = new DevToolsPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  try {
    await waitFor(page, `location.origin === ${JSON.stringify(webOrigin)}`, "测评站点加载");

    await login(page, teacherEmail);
    const courseResponse = await api(page, "/courses", {
      method: "POST",
      body: { title: "R3-E 结果可见性浏览器回归", term: "2026 秋" },
    });
    assert.equal(courseResponse.status, 201, "创建隔离课程失败");
    const courseId = courseResponse.body.data.id;

    await login(page, studentEmail);
    const studentResponse = await api(page, "/me");
    assert.equal(studentResponse.status, 200);
    const studentId = studentResponse.body.data.id;

    await login(page, teacherEmail);
    const membership = await api(page, `/courses/${courseId}/members`, {
      method: "POST",
      body: { user_id: studentId, role: "student" },
    });
    assert.equal(membership.status, 201, "将隔离学生加入课程失败");

    const question = await api(page, `/courses/${courseId}/questions`, {
      method: "POST",
      body: {
        type: "single",
        stem: "本地浏览器回归题：实验者操纵的变量是什么？",
        options: [
          { key: "A", text: "自变量", is_correct: true },
          { key: "B", text: "因变量", is_correct: false },
        ],
        difficulty: 1,
        explanation: "自变量是由实验者操纵的变量。",
        evidence_ids: ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
      },
    });
    assert.equal(question.status, 201, "创建隔离测评题失败");
    const questionId = question.body.data.id;
    const reviewed = await api(page, `/questions/${questionId}/review`, {
      method: "POST",
      body: { action: "approve", version: 1, comment: "浏览器回归合成题审核" },
    });
    assert.equal(reviewed.status, 200, "审核隔离题目失败");
    const publishedQuestion = await api(page, `/questions/${questionId}/publish`, {
      method: "POST",
    });
    assert.equal(publishedQuestion.status, 200, "发布隔离题目失败");
    const questionVersionId = question.body.data.current_version.id;

    const assessment = await api(page, `/courses/${courseId}/assessments`, {
      method: "POST",
      body: {
        title: "R3-E 教师手动发布结果回归",
        question_ids: [questionId],
        purpose: "practice",
        result_visibility_policy: "manual_release",
        ai_policy: "disabled",
        points_per_question: 1,
      },
    });
    assert.equal(assessment.status, 201, "创建隔离测评失败");
    const assessmentId = assessment.body.data.id;
    const publishedAssessment = await api(page, `/assessments/${assessmentId}/publish`, {
      method: "POST",
    });
    assert.equal(publishedAssessment.status, 200, "发布隔离测评失败");

    await login(page, studentEmail);
    const started = await api(page, `/assessments/${assessmentId}/attempts`, { method: "POST" });
    assert.equal(started.status, 201, "学生开始隔离测评失败");
    const attemptId = started.body.data.attempt_id;
    const saved = await api(page, `/attempts/${attemptId}/answers/${questionVersionId}`, {
      method: "PUT",
      body: { answer_version: 1, response: { selected_keys: ["A"] } },
    });
    assert.equal(saved.status, 200, "保存合成答案失败");
    const submitted = await api(page, `/attempts/${attemptId}/submit`, { method: "POST" });
    assert.equal(submitted.status, 200, "提交隔离测评失败");
    assert.ok(submitted.body.data.score == null, "提交响应泄漏了未开放分数");

    await page.send("Page.navigate", { url: `${assessmentPageUrl}?course_id=${courseId}` });
    await waitFor(page, "document.body?.innerText.includes('查看结果状态')", "学生结果列表");
    await page.evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.includes('查看结果状态'))?.click()`);
    await waitFor(page, "document.body?.innerText.includes('结果尚未按测评策略开放')", "学生看到延迟开放提示");
    const beforeRelease = await api(page, `/attempts/${attemptId}/result`);
    assert.equal(beforeRelease.status, 403);
    assert.equal(beforeRelease.body.error?.code, "ASSESSMENT_RESULT_NOT_RELEASED");

    await login(page, teacherEmail);
    const teacherRows = await api(page, `/courses/${courseId}/assessments`);
    const currentRow = teacherRows.body.data.find((row) => row.id === assessmentId);
    assert.equal(currentRow?.status, "published", "隔离测评列表中状态不是 published");
    assert.equal(currentRow?.result_visibility_policy, "manual_release");
    assert.equal(currentRow?.results_released_at, null);
    await page.send("Page.navigate", { url: `${webOrigin}/teacher/courses/${courseId}/assessments` });
    await waitFor(page, "document.body?.innerText.includes('R3-E 教师手动发布结果回归')", "教师测评列表");
    const releaseButtonFound = await waitFor(page, "[...document.querySelectorAll('button')].some(button => button.textContent.includes('手动发布结果'))", "手动发布命令").catch(async (error) => {
      const text = await page.evaluate("document.body?.innerText ?? ''");
      throw new Error(`${error.message}; teacher item: ${JSON.stringify(currentRow)}; page: ${text.slice(-1200)}`);
    });
    assert.ok(releaseButtonFound);
    await page.evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.includes('手动发布结果'))?.click()`);
    await waitFor(page, "document.body?.innerText.includes('测验结果已发布给学生')", "教师发布成功提示");

    await login(page, studentEmail);
    await page.send("Page.navigate", { url: `${assessmentPageUrl}?course_id=${courseId}` });
    await waitFor(page, "document.body?.innerText.includes('查看结果状态')", "学生重新打开结果列表");
    await page.evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.includes('查看结果状态'))?.click()`);
    await waitFor(page, "document.body?.innerText.includes('测验结果')", "教师发布后学生结果可见");
    const afterRelease = await api(page, `/attempts/${attemptId}/result`);
    assert.equal(afterRelease.status, 200);
    assert.equal(afterRelease.body.data.attempt_id, attemptId);
    assert.equal(afterRelease.body.data.score, 1);

    const evidenceDir = join(process.env.TEMP ?? tmpdir(), "r3-e-assessment-result-policy");
    await mkdir(evidenceDir, { recursive: true });
    const screenshotPath = join(evidenceDir, "student-result-after-release.png");
    const screenshot = await page.send("Page.captureScreenshot", { format: "png" });
    await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
    console.log(JSON.stringify({
      result_hidden_before_release: true,
      student_result_status_before_release: beforeRelease.status,
      teacher_manual_release_completed: true,
      student_result_status_after_release: afterRelease.status,
      score_exposed_only_after_release: true,
      screenshot: screenshotPath,
    }));
  } finally {
    page.close();
  }
}

await main();
