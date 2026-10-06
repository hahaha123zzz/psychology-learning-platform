/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI005_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI005_STUDENT_EMAIL;
const password = process.env.UI005_STUDENT_PASSWORD;
const courseTitle = "实验心理学｜学生端合成演示";
const assessmentTitle = "合成练习：实验变量辨析（图表版）";
const questionStem = "【本地合成演示】研究者操纵的变量是什么？";
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

    const beforeReviewsResponse = await readApi(page, "/review-tasks?due_only=false");
    assert.equal(beforeReviewsResponse.status, 200);
    const beforeReviews = beforeReviewsResponse.body.data.filter((item) => item.course_id === course.id);
    const beforeReviewIds = new Set(beforeReviews.map((item) => item.id));
    const priorDueReview = beforeReviews.find((item) => item.reason === "wrong_answer"
      && item.question?.stem === questionStem
      && Date.parse(item.due_at) <= Date.now());

    const practicePath = `/student/courses/${course.id}/practice`;
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

    await assessmentRow.getByRole("button", { name: "开始练习", exact: true }).click();
    const questionCard = page.locator(".attempt-question").filter({ hasText: questionStem });
    await questionCard.waitFor({ state: "visible", timeout: 20_000 });
    await questionCard.locator("label").filter({ hasText: "B. 因变量" }).locator("input").check();
    await questionCard.getByRole("status").filter({ hasText: "已保存" }).waitFor({ state: "visible", timeout: 20_000 });
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
    const generatedReview = afterReviews.find((item) => !beforeReviewIds.has(item.id)
      && item.reason === "wrong_answer"
      && item.question?.stem === questionStem);
    assert.ok(generatedReview, "错答后必须由 API 生成新的 pending wrong_answer review task");
    assert.equal(generatedReview.status, "pending");
    assert.equal(generatedReview.question.options.find((option) => option.key === "A")?.text, "自变量",
      "Review 复用的不可变题目版本应含已知正确选项 A");
    assert.equal(generatedReview.question.options.find((option) => option.key === "B")?.text, "因变量");

    const reviewRows = page.locator(".practice-grid > .support-panel").first().locator(".review-row");
    const generatedIndex = afterReviews.findIndex((item) => item.id === generatedReview.id);
    assert.ok(generatedIndex >= 0);
    const generatedRow = reviewRows.nth(generatedIndex);
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
      await generatedRow.getByRole("status").filter({ hasText: "尚未到复习时间" }).waitFor({ state: "visible" });
      assert.ok(afterReviews.some((item) => item.id === generatedReview.id && item.status === "pending"),
        "未到期 Review 应保持 pending");
    }

    let completedDueReviewId = generatedIsDue ? generatedReview.id : null;
    if (!generatedIsDue && priorDueReview) {
      const dueIndex = afterReviews.findIndex((item) => item.id === priorDueReview.id);
      assert.ok(dueIndex >= 0, "原有 due task 应仍出现在 Review 列表");
      const dueRow = reviewRows.nth(dueIndex);
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
