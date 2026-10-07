/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI005_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI005_STUDENT_EMAIL;
const password = process.env.UI005_STUDENT_PASSWORD;
const resumeSyntheticAttempt = process.env.UI005_RESUME_SYNTHETIC_ATTEMPT === "true";
const courseTitle = "实验心理学｜学生端合成演示";
const assessmentTitle = "合成练习：实验变量辨析（五题版）";
const questionStem = "【本地合成演示】研究者操纵的变量是什么？";
const questionStems = {
  multiple: "【本地合成演示】哪些做法有助于控制无关变量？",
  trueFalse: "【本地合成演示】因变量是研究者测量的结果。",
  shortAnswer: "【本地合成演示】用一句话说明控制组的作用。",
  essay: "【本地合成演示】简述研究者如何用实验比较学习时间对回忆的影响。",
};
const browserPath = process.env.UI005_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password) {
  throw new Error("请提供 V0.9 本地 synthetic 学生账号；本脚本不会启动服务或 seed 数据。");
}

async function readApi(page, path, init = {}) {
  return page.evaluate(async ({ requestPath, requestInit }) => {
    const response = await fetch(`/api/v1${requestPath}`, {
      credentials: "include",
      ...requestInit,
      headers: requestInit.body ? { "Content-Type": "application/json" } : undefined,
      body: requestInit.body ? JSON.stringify(requestInit.body) : undefined,
    });
    const body = await response.json();
    return { status: response.status, body };
  }, { requestPath: path, requestInit: init });
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 20 });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  let formalGuardObserved = false;

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    const coursesResponse = await readApi(page, "/courses");
    assert.equal(coursesResponse.status, 200, "学生课程列表应由真实 API 返回");
    const course = coursesResponse.body.data.find((item) => item.title === courseTitle);
    assert.ok(course, "应存在已 seed 的合成演示课程");
    const assessmentResponse = await readApi(page, `/courses/${course.id}/assessments`);
    assert.equal(assessmentResponse.status, 200);
    const assessment = assessmentResponse.body.data.find((item) => item.title === assessmentTitle);
    assert.ok(assessment, "应存在已 seed 的合成练习");
    assert.equal(assessment.purpose, "practice", "目标测评必须是 practice");
    const activeAttemptId = assessment.current_attempt_id ?? null;
    assert.ok(!activeAttemptId || resumeSyntheticAttempt,
      "发现活动 attempt；只有显式设置 UI005_RESUME_SYNTHETIC_ATTEMPT=true 才能继续本地 synthetic attempt");
    const detailResponse = await readApi(page, `/assessments/${assessment.id}`);
    assert.equal(detailResponse.status, 200);
    assert.equal(detailResponse.body.data.items.length, 5, "合成练习应包含五个交互题目");
    const practiceQuestions = detailResponse.body.data.items;
    assert.deepEqual(new Set(practiceQuestions.map((item) => item.type)),
      new Set(["single", "multiple", "true_false", "short_answer", "essay"]));
    const syntheticQuestion = practiceQuestions.find((item) => item.stem === questionStem);
    assert.ok(syntheticQuestion, "合成练习必须包含目标单选题");
    assert.equal(syntheticQuestion.stem, questionStem);
    assert.equal(syntheticQuestion.options.find((option) => option.key === "A")?.text, "自变量");
    assert.equal(syntheticQuestion.options.find((option) => option.key === "B")?.text, "因变量");

    const beforeReviewsResponse = await readApi(page, "/review-tasks?due_only=false");
    assert.equal(beforeReviewsResponse.status, 200);
    const beforeReviews = beforeReviewsResponse.body.data.filter((item) => item.course_id === course.id);
    const beforeReviewIds = new Set(beforeReviews.map((item) => item.id));
    const priorDueReview = beforeReviews.find((item) => item.reason === "wrong_answer"
      && item.question_version_id === syntheticQuestion.question_version_id
      && Date.parse(item.due_at) <= Date.now());

    const practicePath = `/student/courses/${course.id}/practice`;
    const businessWrites = [];
    let attemptStart = null;
    let resolveAttemptStart;
    const attemptStartPromise = new Promise((resolve) => { resolveAttemptStart = resolve; });
    page.on("request", (request) => {
      const pathname = new URL(request.url()).pathname;
      if (!pathname.startsWith("/api/v1/") || ["GET", "HEAD", "OPTIONS"].includes(request.method())) return;
      let body = null;
      try { body = request.postDataJSON(); } catch { /* 无 JSON body 的写请求仍需计数。 */ }
      businessWrites.push({ method: request.method(), pathname, body });
    });
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (url.pathname === `/api/v1/assessments/${assessment.id}/attempts` && response.request().method() === "POST") {
        try { attemptStart = (await response.json()).data; } catch { attemptStart = null; }
        resolveAttemptStart(attemptStart);
      }
    });
    await page.route(`**/api/v1/courses/${course.id}/assessments`, async (route) => {
      const response = await route.fetch();
      const envelope = await response.json();
      assert.ok(envelope.data.some((item) => item.id === assessment.id && item.purpose === "practice"));
      formalGuardObserved = true;
      await route.fulfill({
        response,
        json: {
          ...envelope,
          data: [...envelope.data, {
            ...assessment,
            id: "ui005-formal-filter-guard",
            title: "UI-005 formal filter guard",
            purpose: "formal",
          }],
        },
      });
    });
    await page.goto(`${webOrigin}${practicePath}`);
    await page.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
    const assessmentRow = page.locator(".practice-grid > .support-panel").nth(1)
      .locator(".review-row").filter({ hasText: assessmentTitle });
    await assessmentRow.waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await page.getByText("UI-005 formal filter guard", { exact: true }).count(), 0,
      "正式测评 fixture 必须被 StudentPracticePage purpose filter 排除");
    assert.ok(formalGuardObserved, "浏览器必须观察到带 formal guard fixture 的真实课程测评响应");

    await assessmentRow.getByRole("button", { name: /开始练习|恢复练习/, exact: true }).click();
    await attemptStartPromise;
    const questionCard = page.locator(".attempt-question").filter({ hasText: questionStem });
    await questionCard.waitFor({ state: "visible", timeout: 20_000 });
    assert.ok(attemptStart, "attempt start API must return current answer snapshot");
    assert.equal(Boolean(attemptStart.resumed), Boolean(activeAttemptId), "server must resume only the supplied active attempt");
    await questionCard.locator("label").filter({ hasText: "B. 因变量" }).locator("input").check();
    await questionCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });

    const multipleCard = page.locator(".attempt-question").filter({ hasText: questionStems.multiple });
    await multipleCard.waitFor({ state: "visible" });
    await multipleCard.locator("label").filter({ hasText: "A. 统一指导语" }).locator("input").check();
    await multipleCard.locator("label").filter({ hasText: "B. 随机分派被试" }).locator("input").check();
    await multipleCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });

    const trueFalseCard = page.locator(".attempt-question").filter({ hasText: questionStems.trueFalse });
    await trueFalseCard.getByRole("radio", { name: "是" }).check();
    await trueFalseCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });

    const shortAnswerCard = page.locator(".attempt-question").filter({ hasText: questionStems.shortAnswer });
    await shortAnswerCard.getByRole("textbox", { name: "第 4 题文字作答" }).fill("控制组提供比较基准，帮助解释结果是否与干预有关。");
    await shortAnswerCard.getByRole("textbox", { name: "第 4 题文字作答" }).blur();
    await shortAnswerCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });

    const essayCard = page.locator(".attempt-question").filter({ hasText: questionStems.essay });
    await essayCard.getByRole("textbox", { name: "第 5 题文字作答" }).fill("操纵学习时间并测量回忆表现，同时统一指导语或随机分派被试。");
    await essayCard.getByRole("textbox", { name: "第 5 题文字作答" }).blur();
    await essayCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });

    await page.getByRole("button", { name: "提交练习", exact: true }).click();
    await page.getByRole("heading", { name: "练习完成", exact: true }).waitFor({ state: "visible", timeout: 20_000 });
    await page.getByRole("button", { name: "返回练习", exact: true }).click();
    await assessmentRow.waitFor({ state: "visible", timeout: 20_000 });

    await page.waitForFunction(async ({ courseId, priorIds }) => {
      const response = await fetch("/api/v1/review-tasks?due_only=false");
      if (!response.ok) return false;
      const envelope = await response.json();
      return envelope.data.some((item) => item.course_id === courseId
        && item.reason === "wrong_answer"
        && item.question?.stem === "【本地合成演示】研究者操纵的变量是什么？"
        && !priorIds.includes(item.id));
    }, { courseId: course.id, priorIds: [...beforeReviewIds] }, { timeout: 20_000 });
    const afterReviewsResponse = await readApi(page, "/review-tasks?due_only=false");
    assert.equal(afterReviewsResponse.status, 200);
    const afterReviews = afterReviewsResponse.body.data.filter((item) => item.course_id === course.id);
    const generatedReviews = afterReviews.filter((item) => !beforeReviewIds.has(item.id)
      && item.reason === "wrong_answer"
      && item.question_version_id === syntheticQuestion.question_version_id);
    assert.equal(generatedReviews.length, 1, "一次错答只能生成一个目标 pending review task");
    const generatedReview = generatedReviews[0];
    assert.ok(generatedReview, "错答后必须由 API 生成新的 pending wrong_answer review task");
    assert.equal(generatedReview.status, "pending");
    assert.equal(generatedReview.question.options.find((option) => option.key === "A")?.text, "自变量",
      "Review 复用的不可变题目版本应含已知正确选项 A");
    assert.equal(generatedReview.question.options.find((option) => option.key === "B")?.text, "因变量");

    const generatedRow = page.locator(`[data-review-task-id="${generatedReview.id}"]`);
    await generatedRow.waitFor({ state: "visible", timeout: 20_000 });
    const generatedChoice = generatedRow.getByRole("combobox", { name: "选择复习答案" });
    assert.match(await generatedChoice.locator('option[value="A"]').textContent(), /A\. 自变量/);
    await generatedChoice.selectOption("A");
    const generatedVerifyButton = generatedRow.getByRole("button", { name: "验证并完成", exact: true });
    const generatedIsDue = Date.parse(generatedReview.due_at) <= Date.now();

    if (generatedIsDue) {
      await generatedVerifyButton.click();
      await page.getByRole("status").filter({ hasText: "复习答案已提交" }).waitFor({ state: "visible", timeout: 20_000 });
      assert.equal(await page.getByRole("status").filter({ hasText: "复习答案已提交" }).getAttribute("aria-live"), "polite");
      await generatedRow.waitFor({ state: "detached", timeout: 20_000 });
    } else {
      assert.ok(await generatedVerifyButton.isDisabled(), "未到期的新任务不得发出必然失败的 verify 请求");
      await generatedRow.getByRole("status").filter({ hasText: "尚未到可复习时间" }).waitFor({ state: "visible" });
      assert.ok(afterReviews.some((item) => item.id === generatedReview.id && item.status === "pending"),
        "未到期 Review 应保持 pending");
    }

    let completedDueReviewId = generatedIsDue ? generatedReview.id : null;
    if (!generatedIsDue && priorDueReview) {
      const dueRow = page.locator(`[data-review-task-id="${priorDueReview.id}"]`);
      await dueRow.waitFor({ state: "visible" });
      assert.equal(priorDueReview.question.options.find((option) => option.key === "A")?.text, "自变量");
      await dueRow.getByRole("combobox", { name: "选择复习答案" }).selectOption("A");
      await dueRow.getByRole("button", { name: "验证并完成", exact: true }).click();
      const success = page.getByRole("status").filter({ hasText: "复习答案已提交" });
      await success.waitFor({ state: "visible", timeout: 20_000 });
      assert.equal(await success.getAttribute("aria-live"), "polite", "复习成功应通过 live region 播报");
      await dueRow.waitFor({ state: "detached", timeout: 20_000 });
      completedDueReviewId = priorDueReview.id;
    }

    if (completedDueReviewId) {
      const completedResponse = await readApi(page, "/review-tasks?due_only=false");
      assert.ok(!completedResponse.body.data.some((item) => item.id === completedDueReviewId),
        "验证完成后，pending 列表应不再包含已完成任务");
    }
    const starts = businessWrites.filter((item) => item.method === "POST"
      && item.pathname === `/api/v1/assessments/${assessment.id}/attempts`);
    const answerWrites = businessWrites.filter((item) => item.method === "PUT"
      && item.pathname.includes("/answers/"));
    const submissions = businessWrites.filter((item) => item.method === "POST"
      && /^\/api\/v1\/attempts\/[^/]+\/submit$/.test(item.pathname));
    const verifyWrites = businessWrites.filter((item) => item.method === "POST"
      && /^\/api\/v1\/review-tasks\/[^/]+\/verify$/.test(item.pathname));
    assert.equal(starts.length, 1, "本脚本只创建一次该合成练习 attempt");
    const savedAnswers = new Map((attemptStart.answers ?? []).map((answer) => [answer.question_version_id, answer.response]));
    for (const write of answerWrites) {
      const questionVersionId = write.pathname.split("/answers/")[1];
      savedAnswers.set(questionVersionId, write.body.response);
    }
    assert.equal(savedAnswers.size, 5, "五种交互题最终都必须有服务端保存的答案");
    const answeredQuestionIds = new Set(answerWrites.map((item) => item.pathname.split("/answers/")[1]));
    assert.equal(answeredQuestionIds.size + (activeAttemptId ? (attemptStart.answers ?? []).filter((answer) => !answeredQuestionIds.has(answer.question_version_id)).length : 0), 5,
      "五种交互题都必须有保存答案；多选允许逐次保存选项变化");
    if (!activeAttemptId) assert.equal(answerWrites.length, 6, "新 attempt 对五题执行五次保存，多选题的两次勾选分别保存");
    const singleAnswer = savedAnswers.get(syntheticQuestion.question_version_id);
    assert.deepEqual(singleAnswer?.selected_keys, ["B"], "目标错答必须只选因变量");
    const multipleQuestion = practiceQuestions.find((item) => item.type === "multiple");
    const multipleAnswer = savedAnswers.get(multipleQuestion.question_version_id);
    assert.deepEqual([...multipleAnswer.selected_keys].sort(), ["A", "B"]);
    const trueFalseQuestion = practiceQuestions.find((item) => item.type === "true_false");
    const trueFalseAnswer = savedAnswers.get(trueFalseQuestion.question_version_id);
    assert.equal(trueFalseAnswer.selected_keys, true);
    const shortAnswerQuestion = practiceQuestions.find((item) => item.stem === questionStems.shortAnswer);
    const shortAnswer = savedAnswers.get(shortAnswerQuestion.question_version_id);
    assert.match(shortAnswer.text, /比较基准/);
    const essayQuestion = practiceQuestions.find((item) => item.stem === questionStems.essay);
    const essay = savedAnswers.get(essayQuestion.question_version_id);
    assert.match(essay.text, /操纵学习时间/);
    assert.equal(submissions.length, 1, "本脚本只提交一次错误作答");
    assert.equal(verifyWrites.length, completedDueReviewId ? 1 : 0,
      "只在已有到期合成复习项时验证一次；绝不提前验证新建的未来任务");
    if (verifyWrites.length) assert.deepEqual(verifyWrites[0].body.response.selected_keys, ["A"]);
    assert.ok(businessWrites.every((item) => item.pathname === `/api/v1/assessments/${assessment.id}/attempts`
      || /^\/api\/v1\/attempts\/[^/]+\/answers\/[A-Z0-9]{26}$/.test(item.pathname)
      || /^\/api\/v1\/attempts\/[^/]+\/submit$/.test(item.pathname)
      || /^\/api\/v1\/review-tasks\/[^/]+\/verify$/.test(item.pathname)),
    `只允许合成题的一次错误练习和最多一次到期 Review 验证：${JSON.stringify(businessWrites)}`);
    assert.deepEqual(pageErrors, [], "Practice→Review should not produce browser errors");
    console.log(JSON.stringify({
      assessment: assessmentTitle,
      wrong_answer_submitted: "B / 因变量",
      generated_review_pending: !generatedIsDue,
      generated_correct_option: "A / 自变量",
      formal_purpose_filtered: true,
      completed_due_review: Boolean(completedDueReviewId),
      success_announced_when_completed: Boolean(completedDueReviewId),
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
