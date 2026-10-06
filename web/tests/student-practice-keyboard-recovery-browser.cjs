/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI021_WEB_ORIGIN ?? "http://127.0.0.1:3216";
const browserPath = process.env.UI021_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";
const courseId = "synthetic-course-021";
const assessmentId = "synthetic-practice-021";
const attemptId = "synthetic-attempt-021";
const questions = [
  {
    question_version_id: "01AAAAAAAAAAAAAAAAAAAAAAAA",
    order_no: 1,
    type: "single",
    stem: "合成单选：选择控制变量示例。",
    options: [{ key: "A", text: "固定实验时长" }, { key: "B", text: "改变实验条件" }],
  },
  {
    question_version_id: "01BBBBBBBBBBBBBBBBBBBBBBBB",
    order_no: 2,
    type: "multiple",
    stem: "合成多选：选择两项记录。",
    options: [{ key: "A", text: "记录样本" }, { key: "B", text: "记录时间" }, { key: "C", text: "跳过记录" }],
  },
  {
    question_version_id: "01CCCCCCCCCCCCCCCCCCCCCCCC",
    order_no: 3,
    type: "true_false",
    stem: "合成判断：记录结果有助于复核。",
  },
  {
    question_version_id: "01DDDDDDDDDDDDDDDDDDDDDDDD",
    order_no: 4,
    type: "short_answer",
    stem: "合成简答：用一句话描述观察目标。",
  },
  {
    question_version_id: "01EEEEEEEEEEEEEEEEEEEEEEEE",
    order_no: 5,
    type: "essay",
    stem: "合成论述：说明比较两组结果时会记录什么。",
  },
];
const assessment = {
  id: assessmentId,
  title: "UI-021 本地合成键盘练习",
  purpose: "practice",
  availability: "open",
  ai_policy: "disabled",
  current_attempt_id: attemptId,
};
const detail = { id: assessmentId, title: assessment.title, items: questions };
const savedAnswers = new Map([
  [questions[0].question_version_id, { selected_keys: ["A"] }],
]);
const answerVersions = new Map(questions.map((question) => [question.question_version_id, 1]));
const businessWrites = [];
const unexpectedRequests = [];
const perQuestionWrites = new Map();
let firstSingleWriteFailed = false;
let secondSingleWriteSaved = false;

function envelope(data) {
  return { data, meta: { request_id: "synthetic-ui021", server_time: "2026-10-06T00:00:00Z" } };
}

function respond(route, status, body) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 8 });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let body = null;
    try { body = request.postDataJSON(); } catch { /* mock只记录 JSON 写入；无 body 的请求仍计数。 */ }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) businessWrites.push({ method, path, body });

    if (method === "GET" && path === "/api/v1/me") {
      return respond(route, 200, envelope({ platform_roles: ["student"] }));
    }
    if (method === "GET" && path === "/api/v1/courses") {
      return respond(route, 200, envelope([{ id: courseId, title: "本地合成课程" }]));
    }
    if (method === "GET" && path === `/api/v1/courses/${courseId}/assessments`) {
      return respond(route, 200, envelope([assessment]));
    }
    if (method === "GET" && path === "/api/v1/review-tasks") {
      return respond(route, 200, envelope([]));
    }
    if (method === "GET" && path === `/api/v1/assessments/${assessmentId}`) {
      return respond(route, 200, envelope(detail));
    }
    if (method === "POST" && path === `/api/v1/assessments/${assessmentId}/attempts`) {
      return respond(route, 200, envelope({
        attempt_id: attemptId,
        resumed: true,
        answers: [...savedAnswers.entries()].map(([question_version_id, response]) => ({
          question_version_id,
          response,
          answer_version: answerVersions.get(question_version_id),
          flagged: false,
        })),
      }));
    }
    if (method === "GET" && path === "/api/v1/student/labs/catalog") {
      return respond(route, 200, envelope([]));
    }
    if (method === "GET" && path === "/api/v1/student/labs/active") {
      return respond(route, 200, envelope(null));
    }
    const answerMatch = path.match(new RegExp(`^/api/v1/attempts/${attemptId}/answers/([A-Z0-9]{26})$`));
    if (method === "PUT" && answerMatch) {
      const questionId = answerMatch[1];
      const count = (perQuestionWrites.get(questionId) ?? 0) + 1;
      perQuestionWrites.set(questionId, count);
      if (questionId === questions[0].question_version_id && count === 1) {
        firstSingleWriteFailed = true;
        return respond(route, 503, { error: { code: "SYNTHETIC_SAVE_FAILURE", message: "合成保存失败，请重新编辑后重试。", retryable: true } });
      }
      savedAnswers.set(questionId, body.response);
      const nextVersion = (answerVersions.get(questionId) ?? 1) + 1;
      answerVersions.set(questionId, nextVersion);
      if (questionId === questions[0].question_version_id && count === 2) secondSingleWriteSaved = true;
      return respond(route, 200, envelope({ answer_version: nextVersion }));
    }

    unexpectedRequests.push(`${method} ${path}`);
    return respond(route, 404, { error: { code: "MOCK_ROUTE_NOT_ALLOWED", message: "此 UI-021 mock route 未开放。" } });
  });

  try {
    const practicePath = `/student/courses/${courseId}/practice`;
    await page.goto(`${webOrigin}${practicePath}`);
    await page.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
    await page.getByRole("button", { name: "恢复练习", exact: true }).click();
    const single = page.locator(".attempt-question").filter({ hasText: questions[0].stem });
    await single.waitFor({ state: "visible" });

    const savedChoice = single.getByRole("radio", { name: "A. 固定实验时长" });
    const unsavedChoice = single.getByRole("radio", { name: "B. 改变实验条件" });
    assert.equal(await savedChoice.isChecked(), true, "打开 attempt 首屏只应反映服务端已有答案");
    await unsavedChoice.focus();
    await page.keyboard.press("Space");
    await single.getByRole("status").filter({ hasText: "保存失败" }).waitFor({ state: "visible" });
    await page.getByRole("alert").filter({ hasText: "答案保存失败" }).waitFor({ state: "visible" });
    assert.equal(await page.getByRole("button", { name: "提交练习", exact: true }).isDisabled(), true,
      "保存失败时不得提交本地未保存答案");
    assert.equal(savedAnswers.get(questions[0].question_version_id).selected_keys[0], "A",
      "第一次失败不能修改 mock 服务端 attempt");

    await page.reload();
    await page.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
    await page.getByRole("button", { name: "恢复练习", exact: true }).click();
    const restoredSingle = page.locator(".attempt-question").filter({ hasText: questions[0].stem });
    await restoredSingle.waitFor({ state: "visible" });
    assert.equal(await restoredSingle.getByRole("radio", { name: "A. 固定实验时长" }).isChecked(), true,
      "刷新后必须由 GET/attempt resume 返回服务端保存的 A");
    assert.equal(await restoredSingle.getByRole("radio", { name: "B. 改变实验条件" }).isChecked(), false,
      "刷新后未保存的本地 B 不得残留或显示成功");
    assert.equal((await restoredSingle.getByRole("status").innerText()).trim(), "已保存",
      "成功状态只对应服务端恢复的 A");

    const retryChoice = restoredSingle.getByRole("radio", { name: "B. 改变实验条件" });
    await retryChoice.focus();
    await page.keyboard.press("Space");
    await restoredSingle.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible" });
    assert.equal(savedAnswers.get(questions[0].question_version_id).selected_keys[0], "B",
      "用户再次键盘选择后，成功 PUT 才更新服务端答案");

    const multiple = page.locator(".attempt-question").filter({ hasText: questions[1].stem });
    for (const name of ["A. 记录样本", "B. 记录时间"]) {
      const checkbox = multiple.getByRole("checkbox", { name });
      await checkbox.focus();
      await page.keyboard.press("Space");
    }
    await multiple.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible" });
    assert.deepEqual(savedAnswers.get(questions[1].question_version_id).selected_keys, ["A", "B"]);

    const trueFalse = page.locator(".attempt-question").filter({ hasText: questions[2].stem });
    const falseRadio = trueFalse.getByRole("radio", { name: "否" });
    await falseRadio.focus();
    await page.keyboard.press("Space");
    await trueFalse.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible" });
    assert.equal(savedAnswers.get(questions[2].question_version_id).selected_keys, false,
      "false 是已保存的判断题答案，也必须计入已答并显示已保存");
    assert.match(await page.locator(".attempt-header").innerText(), /3 \/ 5 已作答/);

    const shortAnswer = page.locator(".attempt-question").filter({ hasText: questions[3].stem });
    const shortTextbox = shortAnswer.getByRole("textbox", { name: "第 4 题文字作答" });
    await shortTextbox.focus();
    await shortTextbox.pressSequentially("typed short response");
    await shortAnswer.getByRole("status").filter({ hasText: "编辑中，尚未保存" }).waitFor({ state: "visible" });
    await shortTextbox.press("Tab");
    await shortAnswer.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible" });
    assert.equal(savedAnswers.get(questions[3].question_version_id).text, "typed short response");

    const essay = page.locator(".attempt-question").filter({ hasText: questions[4].stem });
    const essayTextbox = essay.getByRole("textbox", { name: "第 5 题文字作答" });
    await essayTextbox.focus();
    await essayTextbox.pressSequentially("typed essay response");
    await essayTextbox.press("Tab");
    await essay.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible" });
    assert.equal(savedAnswers.get(questions[4].question_version_id).text, "typed essay response");

    assert.equal(firstSingleWriteFailed, true, "首个单选 PUT 被 mock 为明确可重试失败");
    assert.equal(secondSingleWriteSaved, true, "二次键盘编辑触发并保存成功的 PUT");
    assert.deepEqual(unexpectedRequests, [], "浏览器只能调用显式合成 mock 读取和指定答案保存");
    assert.ok(businessWrites.every((write) =>
      (write.method === "POST" && write.path === `/api/v1/assessments/${assessmentId}/attempts`)
      || (write.method === "PUT" && new RegExp(`^/api/v1/attempts/${attemptId}/answers/[A-Z0-9]{26}$`).test(write.path))),
    `mock browser 不得触发练习以外的写入：${JSON.stringify(businessWrites)}`);
    assert.deepEqual(pageErrors, [], "Practice mock browser should not produce page errors");
    console.log(JSON.stringify({
      mock_only: true,
      keyboard_question_types: ["single", "multiple", "true_false(false)", "short_answer", "essay"],
      first_put_failed_and_accessible: firstSingleWriteFailed,
      unsaved_local_answer_discarded_on_refresh: true,
      server_saved_answer_restored: true,
      keyboard_reedit_saved: secondSingleWriteSaved,
      business_write_paths: [...new Set(businessWrites.map(({ method, path }) => `${method} ${path}`))],
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
