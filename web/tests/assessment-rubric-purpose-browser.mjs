// R3-E 隔离浏览器回归：验证 formal 用途与 Rubric 均拒绝作者自审，并由另一位教师批准。
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webOrigin = process.env.R3_E_WEB_ORIGIN ?? "http://127.0.0.1:3214";
const devtoolsOrigin = process.env.R3_E_CDP_ORIGIN ?? "http://127.0.0.1:9314";
const authorEmail = process.env.R3_E_TEACHER_EMAIL;
const reviewerEmail = process.env.R3_E_REVIEWER_EMAIL;
const password = process.env.R3_E_E2E_PASSWORD ?? "r3-e-local-only-password";
assert.ok(authorEmail && reviewerEmail, "缺少 R3-E 隔离作者/审核教师账号环境变量");
assert.notEqual(authorEmail, reviewerEmail, "作者和审核教师必须是不同账号");

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class DevToolsPage {
  #socket;
  #nextId = 0;
  #pending = new Map();
  #opened;
  #traceEvents = [];
  #traceComplete;

  constructor(url) {
    this.#socket = new WebSocket(url);
    this.#opened = new Promise((resolve, reject) => {
      this.#socket.addEventListener("open", resolve, { once: true });
      this.#socket.addEventListener("error", reject, { once: true });
    });
    this.#socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.method === "Tracing.dataCollected") {
        this.#traceEvents.push(...(message.params.value ?? []));
        return;
      }
      if (message.method === "Tracing.tracingComplete") {
        this.#traceComplete?.();
        return;
      }
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

  async startTrace() {
    await this.send("Tracing.start", {
      categories: "devtools.timeline,blink.user_timing,loading,latencyInfo",
      transferMode: "ReportEvents",
    });
  }

  async saveTrace(path) {
    let resolveTrace;
    const completed = new Promise((resolve) => { resolveTrace = resolve; });
    this.#traceComplete = resolveTrace;
    await this.send("Tracing.end");
    await Promise.race([completed, pause(10_000)]);
    await writeFile(path, JSON.stringify({ traceEvents: this.#traceEvents, displayTimeUnit: "ms" }));
    return this.#traceEvents.length;
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
  return (await api(page, "/me")).body.data.id;
}

async function fillQuestionField(page, questionStem, labelText, value) {
  const expression = `(() => {
    const card = [...document.querySelectorAll('.question-card')].find(node => node.textContent.includes(${JSON.stringify(questionStem)}));
    if (!card) return false;
    const label = [...card.querySelectorAll('label')].find(node => node.textContent.includes(${JSON.stringify(labelText)}));
    const field = label?.querySelector('textarea, input, select');
    if (!field) return false;
    const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : field instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(field, ${JSON.stringify(value)});
    field.dispatchEvent(new Event('input', {bubbles: true}));
    field.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
  })()`;
  assert.equal(await page.evaluate(expression), true, `未找到题目字段：${labelText}`);
}

async function clickQuestionButton(page, questionStem, buttonText, nestedCard = false) {
  const expression = `(() => {
    const outer = [...document.querySelectorAll('.question-card')].find(node => node.textContent.includes(${JSON.stringify(questionStem)}));
    if (!outer) return false;
    const scope = ${nestedCard ? "[...outer.querySelectorAll('.question-card')].find(node => node.textContent.includes('draft'))" : "outer"};
    const button = [...(scope ?? outer).querySelectorAll('button')].find(node => node.textContent.includes(${JSON.stringify(buttonText)}));
    button?.click();
    return Boolean(button);
  })()`;
  assert.equal(await page.evaluate(expression), true, `未找到操作按钮：${buttonText}`);
}

async function main() {
  const landingUrl = `${webOrigin}/teacher`;
  const created = await fetch(`${devtoolsOrigin}/json/new?${encodeURIComponent(landingUrl)}`, {
    method: "PUT",
  });
  assert.ok(created.ok, `Chromium 新建标签失败：HTTP ${created.status}`);
  const target = await created.json();
  const page = new DevToolsPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.startTrace();

  try {
    await waitFor(page, `location.origin === ${JSON.stringify(webOrigin)}`, "教师站点加载");
    const authorId = await login(page, authorEmail);
    const courseResponse = await api(page, "/courses", {
      method: "POST",
      body: { title: "R3-E 用途与 Rubric 双人复核回归", term: "2026 秋" },
    });
    assert.equal(courseResponse.status, 201, "创建隔离课程失败");
    const courseId = courseResponse.body.data.id;
    const reviewerId = await login(page, reviewerEmail);
    assert.notEqual(authorId, reviewerId, "隔离审核教师 ID 与作者相同");
    await login(page, authorEmail);
    const reviewerMembership = await api(page, `/courses/${courseId}/members`, {
      method: "POST",
      body: { user_id: reviewerId, role: "teacher" },
    });
    assert.equal(reviewerMembership.status, 201, "将独立审核教师加入隔离课程失败");

    const stem = "浏览器回归题：说明被试内设计如何控制个体差异。";
    const question = await api(page, `/courses/${courseId}/questions`, {
      method: "POST",
      body: {
        type: "essay",
        stem,
        rubric: "指出同一被试参加多个条件，并说明这可以控制个体差异。",
        difficulty: 2,
        evidence_ids: ["01ARZ3NDEKTSV4RRFFQ69G5FAV"],
      },
    });
    assert.equal(question.status, 201, "创建隔离主观题失败");
    const questionId = question.body.data.id;
    const questionVersionId = question.body.data.current_version.id;
    const reviewed = await api(page, `/questions/${questionId}/review`, {
      method: "POST",
      body: { action: "approve", version: 1, comment: "浏览器回归合成题复核" },
    });
    assert.equal(reviewed.status, 200, "审核隔离主观题失败");
    const publishedQuestion = await api(page, `/questions/${questionId}/publish`, { method: "POST" });
    assert.equal(publishedQuestion.status, 200, "发布隔离主观题失败");

    await page.send("Page.navigate", { url: `${webOrigin}/teacher/courses/${courseId}/assessments` });
    await waitFor(page, `document.body?.innerText.includes(${JSON.stringify(stem)})`, "测评向导及用途/Rubric 区域");
    await fillQuestionField(page, stem, "正式用途复核理由", "题目作者尝试自审，应由系统拒绝。");
    await clickQuestionButton(page, stem, "批准 formal 用途");
    await waitFor(page, "document.body?.innerText.includes('题目作者不能审批自己的正式用途')", "正式用途作者自审被拒");

    await page.evaluate(`(() => {
      const outer = [...document.querySelectorAll('.question-card')].find(node => node.textContent.includes(${JSON.stringify(stem)}));
      const details = [...(outer?.querySelectorAll('details') ?? [])].find(node => node.textContent.includes('创建新的 Rubric 草稿版本'));
      if (details) details.open = true;
      return Boolean(details);
    })()`);
    await fillQuestionField(page, stem, "评分项标识", "design-benefit");
    await fillQuestionField(page, stem, "评分标准", "说明同一被试参加多个条件以及由此控制个体差异的作用。");
    await fillQuestionField(page, stem, "0 分锚点", "未指出同一被试参与多个条件。");
    await fillQuestionField(page, stem, "满分锚点", "明确说明同一被试参加多个条件及控制个体差异的作用。");
    const selectedEvidence = await page.evaluate(`(() => {
      const outer = [...document.querySelectorAll('.question-card')].find(node => node.textContent.includes(${JSON.stringify(stem)}));
      const details = [...(outer?.querySelectorAll('details') ?? [])].find(node => node.textContent.includes('创建新的 Rubric 草稿版本'));
      const select = details?.querySelector('select');
      if (!select || select.options.length < 2) return false;
      select.value = select.options[1].value;
      select.dispatchEvent(new Event('change', {bubbles: true}));
      return true;
    })()`);
    assert.equal(selectedEvidence, true, "没有为题目版本选择证据引用");
    await clickQuestionButton(page, stem, "创建 Rubric 草稿");
    await waitFor(page, "document.body?.innerText.includes('Rubric 草稿版本已创建')", "Rubric 草稿创建成功");
    const rubricRows = await api(page, `/courses/${courseId}/rubrics?question_version_id=${questionVersionId}`);
    assert.equal(rubricRows.status, 200);
    assert.equal(rubricRows.body.data.length, 1);
    const rubricId = rubricRows.body.data[0].id;

    await fillQuestionField(page, stem, "独立审批理由", "作者自审边界浏览器回归验证。");
    await clickQuestionButton(page, stem, "批准此版本", true);
    await waitFor(page, "document.body?.innerText.includes('Rubric 作者不能审核自己的评分依据')", "Rubric 作者自审被拒");

    await login(page, reviewerEmail);
    await page.send("Page.navigate", { url: `${webOrigin}/teacher/courses/${courseId}/assessments` });
    await waitFor(page, `document.body?.innerText.includes(${JSON.stringify(stem)})`, "独立审核教师测评向导");
    await fillQuestionField(page, stem, "正式用途复核理由", "由独立课程教师复核题目与证据，批准正式测评用途。");
    await clickQuestionButton(page, stem, "批准 formal 用途");
    await waitFor(page, "document.body?.innerText.includes('正式测评用途已批准')", "独立教师批准正式用途");
    await fillQuestionField(page, stem, "独立审批理由", "评分项和两端锚点均与引用证据相符，批准此版本。");
    await clickQuestionButton(page, stem, "批准此版本", true);
    await waitFor(page, "document.body?.innerText.includes('Rubric 已批准')", "独立教师批准 Rubric");

    const approvedRows = await api(page, `/courses/${courseId}/rubrics?question_version_id=${questionVersionId}`);
    assert.equal(approvedRows.status, 200);
    assert.equal(approvedRows.body.data[0].status, "approved");
    const preview = await api(page, `/courses/${courseId}/assessments/preview`, {
      method: "POST",
      body: {
        title: "正式用途与 Rubric 发布门禁预览",
        question_ids: [questionId],
        rubric_version_ids: { [questionVersionId]: rubricId },
        purpose: "formal",
        result_visibility_policy: "after_grading",
        ai_policy: "disabled",
        points_per_question: 1,
      },
    });
    assert.equal(preview.status, 200, "正式用途门禁预览请求失败");
    assert.equal(preview.body.data.can_publish, true, JSON.stringify(preview.body.data.blocking_issues));
    const evidenceDirectory = join(tmpdir(), "r3-e-assessment-rubric-purpose");
    await mkdir(evidenceDirectory, { recursive: true });
    const screenshotPath = join(evidenceDirectory, "rubric-purpose-approved.png");
    const screenshot = await page.send("Page.captureScreenshot", { format: "png" });
    await writeFile(screenshotPath, Buffer.from(screenshot.data, "base64"));
    const tracePath = join(evidenceDirectory, "rubric-purpose-trace.json");
    const traceEventCount = await page.saveTrace(tracePath);
    console.log(JSON.stringify({
      author_formal_self_review_rejected: true,
      author_rubric_self_review_rejected: true,
      independent_reviewer_approved_purpose_and_rubric: true,
      formal_assessment_preview_unblocked: true,
      screenshot: screenshotPath,
      trace: tracePath,
      trace_event_count: traceEventCount,
    }));
  } finally {
    page.close();
  }
}

await main();
