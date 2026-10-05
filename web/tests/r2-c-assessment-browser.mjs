// R2-C 独立 Chromium/CDP 测评浏览器验收；仅连接 3203/8203。
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webOrigin = "http://127.0.0.1:3203";
const devtoolsOrigin = "http://127.0.0.1:9223";
const courseId = process.env.R2_C_COURSE_ID;
const assessmentId = process.env.R2_C_ASSESSMENT_ID;
const attemptId = process.env.R2_C_ATTEMPT_ID;
const questionVersionId = process.env.R2_C_QUESTION_VERSION_ID;
const studentEmail = process.env.R2_C_ASSESSMENT_STUDENT_EMAIL ?? "r2-c-student@example.com";
const password = process.env.R2_C_E2E_PASSWORD ?? "r2-c-local-only-password";
if (!courseId || !assessmentId || !attemptId || !questionVersionId) {
  throw new Error("缺少 R2-C 测评场景 ID 环境变量。");
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

async function waitFor(page, expression, label, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await page.evaluate(expression);
    if (value) return value;
    await pause(200);
  }
  throw new Error(`等待浏览器状态超时：${label}`);
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
  if (status !== 200) throw new Error(`隔离浏览器登录失败：HTTP ${status}`);
}

async function main() {
  const attemptUrl = `${webOrigin}/student/assessments?course_id=${encodeURIComponent(courseId)}`;
  const page1 = await newTarget(attemptUrl);
  let page2;
  try {
    await waitFor(page1, `location.origin === ${JSON.stringify(webOrigin)}`, "测评页加载");
    await login(page1);
    await page1.send("Page.navigate", { url: attemptUrl });
    await waitFor(
      page1,
      `document.body?.innerText.includes('研究者操纵的变量是什么？')`,
      "第一个标签恢复测评",
    );
    console.log("browser-stage:first-tab-ready");

    page2 = await newTarget(attemptUrl);
    await waitFor(
      page2,
      `document.body?.innerText.includes('研究者操纵的变量是什么？')`,
      "第二个标签恢复同一测评",
    );
    console.log("browser-stage:second-tab-ready");

    const attemptIds = await page1.evaluate(`(async () => {
      const response = await fetch('/api/v1/assessments/${assessmentId}/attempts', {method:'POST'});
      return {status: response.status, body: await response.json()};
    })()`);
    if (attemptIds.status !== 200) {
      throw new Error(`并发标签续接接口返回 HTTP ${attemptIds.status}`);
    }
    if (attemptIds.body.data.attempt_id !== attemptId) {
      throw new Error("两个标签没有恢复同一服务端 attempt_id");
    }
    console.log("browser-stage:same-attempt");

    await page1.send("Network.enable");
    await page1.send("Network.emulateNetworkConditions", {
      offline: true,
      latency: 0,
      downloadThroughput: 0,
      uploadThroughput: 0,
    });
    await page1.evaluate("document.querySelectorAll('.assessment-item input[type=radio]')[1]?.click()");
    await waitFor(
      page1,
      `document.querySelector('.assessment-item small[role=status]')?.textContent === '保存失败'`,
      "离线保存失败状态",
    );
    const offlineAnswerStayedVisible = await page1.evaluate(
      "document.querySelectorAll('.assessment-item input[type=radio]')[1]?.checked === true",
    );
    console.log("browser-stage:offline-save-error-visible");
    await page1.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
    });
    await page1.evaluate("document.querySelectorAll('.assessment-item input[type=radio]')[0]?.click()");
    await waitFor(
      page1,
      `document.querySelector('.assessment-item small[role=status]')?.textContent === '已保存'`,
      "第一个标签保存答案",
    );
    console.log("browser-stage:first-answer-saved");
    const staleNetworkErrorVisible = await page1.evaluate(
      "document.body?.innerText.includes('请求失败，请稍后重试。') === true",
    );
    if (staleNetworkErrorVisible) {
      throw new Error("离线保存成功重试后仍显示过期的网络错误提示");
    }
    await page2.evaluate("document.querySelectorAll('.assessment-item input[type=radio]')[1]?.click()");
    await waitFor(
      page2,
      `document.querySelector('.assessment-item small[role=status]')?.textContent === '保存失败'`,
      "第二个标签遇到旧 answer_version 冲突",
    );
    console.log("browser-stage:stale-write-conflict");

    await page2.send("Page.reload", { ignoreCache: true });
    const restored = await waitFor(
      page2,
      `(() => {
        const inputs = [...document.querySelectorAll('.assessment-item input[type=radio]')];
        return inputs.length === 2 && inputs[0].checked ? inputs.map(input => input.checked) : null;
      })()`,
      "刷新后恢复服务端已保存答案",
    );
    if (restored[0] !== true || restored[1] !== false) {
      throw new Error("旧标签的本地答案覆盖了服务端已保存值");
    }
    console.log("browser-stage:server-answer-restored");

    await waitFor(
      page1,
      `(() => {
        const text = document.querySelector('.attempt-header strong')?.textContent ?? '';
        if (text === '已到截止时间') return true;
        const match = text.match(/剩余 (\\d+)分(\\d+)秒/);
        return Boolean(match && Number(match[1]) * 60 + Number(match[2]) <= 20);
      })()`,
      "截止前进入断网窗口",
      330_000,
    );
    await page2.send("Network.enable");
    for (const page of [page1, page2]) {
      await page.send("Network.emulateNetworkConditions", {
        offline: true,
        latency: 0,
        downloadThroughput: 0,
        uploadThroughput: 0,
      });
    }
    await waitFor(
      page1,
      `document.body?.innerText.includes('重试提交已保存答案')`,
      "截止时断网，自动提交失败且显示恢复操作",
      30_000,
    );
    await waitFor(
      page2,
      `document.body?.innerText.includes('重试提交已保存答案')`,
      "第二标签显示同一截止恢复操作",
      15_000,
    );
    console.log("browser-stage:offline-at-deadline-retry-visible");
    for (const page of [page1, page2]) {
      await page.send("Network.emulateNetworkConditions", {
        offline: false,
        latency: 0,
        downloadThroughput: -1,
        uploadThroughput: -1,
      });
    }
    await page1.evaluate(`(() => [...document.querySelectorAll('button')].find(button => button.textContent?.includes('重试提交已保存答案'))?.click())()`);
    await waitFor(
      page1,
      `document.body?.innerText.includes('测验结果')`,
      "网络恢复后提交服务端已保存答案",
      20_000,
    );
    await page2.evaluate(`(() => [...document.querySelectorAll('button')].find(button => button.textContent?.includes('重试提交已保存答案'))?.click())()`);
    await waitFor(
      page2,
      `document.body?.innerText.includes('测验结果')`,
      "第二标签重放幂等提交结果",
      20_000,
    );
    console.log("browser-stage:deadline-recovered-in-both-tabs");
    const resultStatus = await page1.evaluate(`(async () => {
      const response = await fetch('/api/v1/attempts/${attemptId}/result');
      return response.status;
    })()`);
    if (resultStatus !== 200) throw new Error(`服务端测评结果读取失败：HTTP ${resultStatus}`);

    const evidenceDirectory = join(process.env.TEMP ?? tmpdir(), "psychology-r2-c");
    await mkdir(evidenceDirectory, { recursive: true });
    let screenshotPath = null;
    try {
      const screenshot = await Promise.race([
        page1.send("Page.captureScreenshot", {
          format: "png",
          captureBeyondViewport: true,
        }),
        pause(8_000).then(() => {
          throw new Error("CDP 截图调用超时");
        }),
      ]);
      screenshotPath = join(evidenceDirectory, "assessment-deadline-result.png");
      await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
    } catch (error) {
      console.warn(`browser-evidence:screenshot-unavailable:${error.message}`);
    }
    console.log(JSON.stringify({
      browser: await page1.evaluate("navigator.userAgent"),
      two_tabs_same_attempt: true,
      offline_save_failed_visible: true,
      offline_answer_stayed_visible: offlineAnswerStayedVisible,
      online_resave_succeeded: true,
      stale_tab_conflict_visible: true,
      refresh_restored_server_answer: true,
      offline_deadline_recovery_visible_in_both_tabs: true,
      result_http_status: resultStatus,
      screenshot: screenshotPath,
      answer_text_logged: false,
    }));
  } finally {
    page2?.close();
    page1.close();
  }
}

await main().catch((error) => {
  console.error("R2-C assessment browser test failed:", error?.stack ?? error);
  process.exitCode = 1;
});
