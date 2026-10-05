// R2-C 浏览器在测评截止后重开页面，恢复服务端已保存 Attempt。
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webOrigin = "http://127.0.0.1:3203";
const devtoolsOrigin = "http://127.0.0.1:9223";
const courseId = process.env.R2_C_COURSE_ID;
const attemptId = process.env.R2_C_ATTEMPT_ID;
const studentEmail = process.env.R2_C_ASSESSMENT_STUDENT_EMAIL;
const password = process.env.R2_C_E2E_PASSWORD ?? "r2-c-local-only-password";
if (!courseId || !attemptId || !studentEmail) {
  throw new Error("缺少 R2-C 截止恢复场景 ID 或测试账号环境变量。");
}

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

async function main() {
  const url = `${webOrigin}/student/assessments?course_id=${encodeURIComponent(courseId)}`;
  const created = await fetch(`${devtoolsOrigin}/json/new?${encodeURIComponent(url)}`, {
    method: "PUT",
  });
  if (!created.ok) throw new Error(`Chromium 创建标签失败：HTTP ${created.status}`);
  const target = await created.json();
  const page = new DevToolsPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  try {
    await waitFor(page, `location.origin === ${JSON.stringify(webOrigin)}`, "测评页面加载");
    const loginStatus = await page.evaluate(`(async () => {
      const response = await fetch('/api/v1/auth/login', {
        method:'POST', credentials:'include', headers:{'content-type':'application/json'},
        body:JSON.stringify({email:${JSON.stringify(studentEmail)},password:${JSON.stringify(password)}})
      });
      return response.status;
    })()`);
    if (loginStatus !== 200) throw new Error(`R2-C 测评账号登录失败：HTTP ${loginStatus}`);
    await page.send("Page.navigate", { url });
    await waitFor(
      page,
      `document.body?.innerText.includes('测验结果')`,
      "截止后只恢复服务端已保存结果",
      45_000,
    );
    const result = await page.evaluate(`(async () => {
      const response = await fetch('/api/v1/attempts/${attemptId}/result');
      const body = await response.json();
      return {status:response.status, attempt_id:body.data?.attempt_id, grading_status:body.data?.grading_status};
    })()`);
    if (result.status !== 200 || result.attempt_id !== attemptId) {
      throw new Error("刷新恢复没有读取同一服务端 Attempt 结果");
    }
    const text = await page.evaluate("document.body?.innerText ?? ''");
    if (!text.includes("评分状态：graded")) {
      throw new Error("截止恢复页面没有展示已完成评分状态");
    }
    const directory = join(process.env.TEMP ?? tmpdir(), "psychology-r2-c");
    await mkdir(directory, { recursive: true });
    const screenshotPath = join(directory, "assessment-closed-attempt-recovered.png");
    const screenshot = await page.send("Page.captureScreenshot", { format: "png" });
    await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
    console.log(JSON.stringify({
      browser_reopened_after_deadline: true,
      same_attempt_result_http_status: result.status,
      grading_status: result.grading_status,
      answer_text_logged: false,
      screenshot: screenshotPath,
    }));
  } finally {
    page.close();
  }
}

await main().catch((error) => {
  console.error("R2-C closed-attempt recovery browser test failed:", error?.stack ?? error);
  process.exitCode = 1;
});
