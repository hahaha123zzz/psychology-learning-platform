// R2-C 提交响应丢失浏览器验收；使用 3203/8203 与独立 CDP Chromium。
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webOrigin = "http://127.0.0.1:3203";
const devtoolsOrigin = "http://127.0.0.1:9223";
const courseId = process.env.R2_C_COURSE_ID;
const assessmentId = process.env.R2_C_ASSESSMENT_ID;
const attemptId = process.env.R2_C_ATTEMPT_ID;
const questionVersionId = process.env.R2_C_QUESTION_VERSION_ID;
const studentEmail = process.env.R2_C_ASSESSMENT_STUDENT_EMAIL;
const password = process.env.R2_C_E2E_PASSWORD ?? "r2-c-local-only-password";
if (!courseId || !assessmentId || !attemptId || !questionVersionId || !studentEmail) {
  throw new Error("缺少 R2-C 提交响应丢失场景 ID 或测试账号环境变量。");
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class DevToolsPage {
  #socket;
  #nextId = 0;
  #pending = new Map();
  #listeners = new Map();
  #opened;

  constructor(url) {
    this.#socket = new WebSocket(url);
    this.#opened = new Promise((resolve, reject) => {
      this.#socket.addEventListener("open", resolve, { once: true });
      this.#socket.addEventListener("error", reject, { once: true });
    });
    this.#socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.method) {
        for (const listener of this.#listeners.get(message.method) ?? []) {
          listener(message.params ?? {});
        }
        return;
      }
      if (message.id === undefined) return;
      const pending = this.#pending.get(message.id);
      if (!pending) return;
      this.#pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result ?? {});
    });
    this.#socket.addEventListener("close", () => {
      for (const pending of this.#pending.values()) {
        pending.reject(new Error("R2-C isolated Chromium CDP connection closed"));
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

  on(method, listener) {
    const listeners = this.#listeners.get(method) ?? new Set();
    listeners.add(listener);
    this.#listeners.set(method, listeners);
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

async function waitFor(page, expression, label, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await page.evaluate(expression);
    if (value) return value;
    await pause(200);
  }
  throw new Error(`等待浏览器状态超时：${label}`);
}

async function newTarget(url) {
  const response = await fetch(`${devtoolsOrigin}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  });
  if (!response.ok) throw new Error(`Chromium 创建标签失败：HTTP ${response.status}`);
  const target = await response.json();
  const page = new DevToolsPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Page.navigate", { url });
  return page;
}

async function login(page) {
  const status = await page.evaluate(`(async () => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({email: ${JSON.stringify(studentEmail)}, password: ${JSON.stringify(password)}}),
    });
    return response.status;
  })()`);
  if (status !== 200) throw new Error(`R2-C 测评测试账号登录失败：HTTP ${status}`);
}

async function main() {
  const attemptUrl = `${webOrigin}/student/assessments?course_id=${encodeURIComponent(courseId)}`;
  const page = await newTarget(attemptUrl);
  try {
    await waitFor(page, `location.origin === ${JSON.stringify(webOrigin)}`, "测评页加载");
    await login(page);
    await page.send("Page.navigate", { url: attemptUrl });
    await waitFor(
      page,
      `document.body?.innerText.includes('研究者操纵的变量是什么？')`,
      "恢复已发布测评",
    );
    await page.evaluate("document.querySelectorAll('.assessment-item input[type=radio]')[0]?.click()");
    await waitFor(
      page,
      `document.querySelector('.assessment-item small[role=status]')?.textContent === '已保存'`,
      "持久化一条测评答案",
    );
    await page.evaluate(`(() => [...document.querySelectorAll('button')].find(button => button.textContent?.includes('检查并提交'))?.click())()`);
    await waitFor(
      page,
      `document.body?.innerText.includes('确认提交测验')`,
      "提交确认状态",
    );

    const submitPath = `/api/v1/attempts/${attemptId}/submit`;
    let resolveIntercept;
    const intercepted = new Promise((resolve) => {
      resolveIntercept = resolve;
    });
    page.on("Fetch.requestPaused", (params) => {
      if (
        !params.responseStatusCode ||
        !params.request.url.includes(submitPath)
      ) return;
      void page.send("Fetch.failRequest", {
        requestId: params.requestId,
        errorReason: "ConnectionReset",
      }).then(() => resolveIntercept(params.responseStatusCode));
    });
    await page.send("Fetch.enable", {
      patterns: [{ urlPattern: `*${submitPath}`, requestStage: "Response" }],
    });
    await page.evaluate(`(() => [...document.querySelectorAll('button')].find(button => button.textContent?.includes('确认提交测验'))?.click())()`);
    const droppedStatus = await Promise.race([
      intercepted,
      pause(15_000).then(() => { throw new Error("没有观察到已提交事务的 HTTP 响应栅栏"); }),
    ]);
    if (droppedStatus !== 200) {
      throw new Error(`提交事务已完成但被拦截的响应状态为 HTTP ${droppedStatus}`);
    }
    await page.send("Fetch.disable");
    await waitFor(
      page,
      `document.body?.innerText.includes('请求失败，请稍后重试。')`,
      "浏览器未确认提交响应并显示失败",
    );

    const persistedResult = await page.evaluate(`(async () => {
      const response = await fetch('/api/v1/attempts/${attemptId}/result');
      const body = await response.json();
      return {status: response.status, attempt_id: body.data?.attempt_id};
    })()`);
    if (persistedResult.status !== 200 || persistedResult.attempt_id !== attemptId) {
      throw new Error("丢失响应后服务端没有返回已提交的 Attempt 结果");
    }

    await page.evaluate(`(() => [...document.querySelectorAll('button')].find(button => button.textContent?.includes('确认提交测验'))?.click())()`);
    await waitFor(
      page,
      `document.body?.innerText.includes('测验结果')`,
      "用户重试后恢复结果页面",
    );
    const replay = await page.evaluate(`(async () => {
      const response = await fetch('/api/v1/attempts/${attemptId}/submit', {method:'POST'});
      const body = await response.json();
      return {status: response.status, idempotent_replay: body.data?.idempotent_replay === true};
    })()`);
    if (replay.status !== 200 || !replay.idempotent_replay) {
      throw new Error("重复提交没有返回同一 Attempt 的幂等回放");
    }

    const evidenceDirectory = join(process.env.TEMP ?? tmpdir(), "psychology-r2-c");
    await mkdir(evidenceDirectory, { recursive: true });
    const screenshot = await page.send("Page.captureScreenshot", { format: "png" });
    const screenshotPath = join(evidenceDirectory, "assessment-submit-response-recovered.png");
    await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
    console.log(JSON.stringify({
      response_status_before_drop: droppedStatus,
      response_dropped_after_server_commit: true,
      page_reported_unconfirmed_submit: true,
      persisted_result_read_after_loss: persistedResult.status,
      retry_result_visible: true,
      duplicate_submit_idempotent: replay.idempotent_replay,
      screenshot: screenshotPath,
      answer_text_logged: false,
    }));
  } finally {
    page.close();
  }
}

await main().catch((error) => {
  console.error("R2-C submit-response-loss browser test failed:", error?.stack ?? error);
  process.exitCode = 1;
});
