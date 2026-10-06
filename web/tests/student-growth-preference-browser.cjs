/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI006_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI006_STUDENT_EMAIL;
const password = process.env.UI006_STUDENT_PASSWORD;
const courseTitle = "实验心理学｜学生端合成演示";
const browserPath = process.env.UI006_CHROME_PATH
  ?? "C:/Users/free/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

if (!email || !password) {
  throw new Error("请提供本地 synthetic 学生账号；脚本不会启动服务、seed 数据或操作其他学生。");
}

async function api(page, path) {
  return page.evaluate(async ({ requestPath }) => {
    const response = await fetch(`/api/v1${requestPath}`, {
      credentials: "include",
    });
    return { status: response.status, body: await response.json() };
  }, { requestPath: path });
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 20 });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  const businessWrites = [];
  const blockedPersonalReads = [];
  let savedBaseline = null;
  let courseId = null;
  let restoreError = null;
  let reviewGuardObserved = false;
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    await page.route((url) => url.pathname === "/api/v1/me/memory"
      || url.pathname.startsWith("/api/v1/me/memory/items")
      || url.pathname.startsWith("/api/v1/me/notifications"), async (route) => {
      blockedPersonalReads.push(new URL(route.request().url()).pathname);
      await route.abort();
    });

    page.on("request", (request) => {
      const url = new URL(request.url());
      if (request.method() !== "GET") businessWrites.push({ method: request.method(), path: url.pathname });
    });

    const courses = await api(page, "/courses");
    assert.equal(courses.status, 200, "课程列表必须来自真实 API");
    const course = courses.body.data.find((item) => item.title === courseTitle);
    assert.ok(course, "应存在已 seed 的合成演示课程");
    courseId = course.id;

    const [overview, knowledge, tabs, reviews] = await Promise.all([
      api(page, `/student/growth/overview?course_id=${courseId}`),
      api(page, `/student/growth/knowledge?course_id=${courseId}`),
      api(page, `/student/growth/tabs?course_id=${courseId}`),
      api(page, "/review-tasks?due_only=false"),
    ]);
    for (const response of [overview, knowledge, tabs, reviews]) assert.equal(response.status, 200);
    assert.equal(overview.body.data.course_id, courseId, "Growth projection must belong to the route course");
    const courseReviews = reviews.body.data.filter((review) => review.course_id === courseId);

    const reviewRoute = (url) => url.pathname === "/api/v1/review-tasks" && url.search === "?due_only=false";
    const reviewHandler = async (route) => {
      const response = await route.fetch();
      const envelope = await response.json();
      reviewGuardObserved = true;
      const otherCourseId = courseId === "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        ? "01ARZ3NDEKTSV4RRFFQ69G5FAW"
        : "01ARZ3NDEKTSV4RRFFQ69G5FAV";
      await route.fulfill({
        response,
        json: {
          ...envelope,
          data: [...envelope.data, {
            id: "ui006-foreign-course-review-guard",
            course_id: otherCourseId,
            reason: "UI-006 cross-course review guard",
            due_at: new Date(Date.now() + 86_400_000).toISOString(),
            status: "pending",
          }],
        },
      });
    };
    await page.route(reviewRoute, reviewHandler);
    await page.goto(`${webOrigin}/student/courses/${courseId}/growth`);
    await page.getByRole("heading", { name: "成长", exact: true }).waitFor({ state: "visible" });
    if (overview.body.data.focus) {
      const focus = page.locator(".growth-focus");
      await focus.waitFor({ state: "visible" });
      for (const value of [
        overview.body.data.focus.knowledge_point,
        overview.body.data.focus.state,
        overview.body.data.focus.state_reason,
        overview.body.data.focus.next_step,
      ]) assert.ok((await focus.innerText()).includes(value), "Growth focus must match service projection fields");
    } else {
      await page.getByText("完成学习或测验后，这里会生成可解释的成长建议。", { exact: true }).waitFor();
    }
    const expectedDueCount = overview.body.data.attention.due_review_count;
    const nextStepSummary = page.locator(".growth-panel").first().locator(".panel-heading span");
    assert.equal((await nextStepSummary.innerText()).trim(), expectedDueCount
      ? `${expectedDueCount} 项到期复习`
      : "状态已更新");
    await page.getByRole("heading", { name: "复习安排", exact: true }).waitFor();
    const reviewPanel = page.locator(".support-panel").filter({ has: page.getByRole("heading", { name: "复习安排" }) });
    assert.equal((await reviewPanel.locator(".panel-heading span").innerText()).trim(), `${courseReviews.length} 项`,
      "Growth review list must use current-route course task count");
    assert.equal(await page.getByText("UI-006 cross-course review guard", { exact: true }).count(), 0,
      "another course's review must not appear on this Growth route");
    assert.ok(reviewGuardObserved);
    assert.equal(await page.locator(".growth-row").count(), knowledge.body.data.length,
      "default knowledge view must match the course-scoped knowledge API");

    await page.unroute(reviewRoute, reviewHandler);
    const preferenceResponse = await api(page, "/me/preferences");
    assert.equal(preferenceResponse.status, 200, "preference baseline must come from the current synthetic student");
    savedBaseline = preferenceResponse.body.data.preferences;
    const baselinePreferences = structuredClone(savedBaseline);
    const targetResponseLength = baselinePreferences.response_length === "DETAILED" ? "CONCISE" : "DETAILED";
    const targetExampleOrder = baselinePreferences.example_order === "EXAMPLE_FIRST" ? "CONCEPT_FIRST" : "EXAMPLE_FIRST";

    await page.goto(`${webOrigin}/student/courses/${courseId}/me`);
    await page.getByRole("heading", { name: "我的", exact: true }).waitFor({ state: "visible" });
    const responseLength = page.getByLabel("回答长度");
    const exampleOrder = page.getByLabel("讲解顺序");
    await responseLength.waitFor({ state: "visible" });
    assert.equal(await responseLength.inputValue(), baselinePreferences.response_length);
    assert.equal(await exampleOrder.inputValue(), baselinePreferences.example_order);
    await responseLength.selectOption(targetResponseLength);
    await exampleOrder.selectOption(targetExampleOrder);
    await page.getByRole("button", { name: "保存偏好", exact: true }).click();
    await page.getByRole("status").filter({ hasText: "偏好已保存。" }).waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await responseLength.inputValue(), targetResponseLength);
    assert.equal(await exampleOrder.inputValue(), targetExampleOrder);
    await page.reload();
    await page.getByLabel("回答长度").waitFor({ state: "visible" });
    assert.equal(await page.getByLabel("回答长度").inputValue(), targetResponseLength,
      "response_length should persist after refresh");
    assert.equal(await page.getByLabel("讲解顺序").inputValue(), targetExampleOrder,
      "example_order should persist after refresh");
    const persisted = await api(page, "/me/preferences");
    assert.equal(persisted.status, 200);
    assert.equal(persisted.body.data.preferences.response_length, targetResponseLength);
    assert.equal(persisted.body.data.preferences.example_order, targetExampleOrder);
    assert.equal(persisted.body.data.version, preferenceResponse.body.data.version + 1);
    assert.deepEqual(
      Object.fromEntries(Object.keys(baselinePreferences).filter((key) => !["response_length", "example_order"].includes(key))
        .map((key) => [key, persisted.body.data.preferences[key]])),
      Object.fromEntries(Object.keys(baselinePreferences).filter((key) => !["response_length", "example_order"].includes(key))
        .map((key) => [key, baselinePreferences[key]])),
      "other preference fields must remain unchanged",
    );
  } finally {
    if (savedBaseline) {
      try {
        await page.goto(`${webOrigin}/student/courses/${courseId}/me`);
        await page.getByRole("heading", { name: "我的", exact: true }).waitFor({ state: "visible" });
        const responseLength = page.getByLabel("回答长度");
        const exampleOrder = page.getByLabel("讲解顺序");
        await responseLength.waitFor({ state: "visible" });
        await responseLength.selectOption(savedBaseline.response_length);
        await exampleOrder.selectOption(savedBaseline.example_order);
        await page.getByRole("button", { name: "保存偏好", exact: true }).click();
        await page.getByRole("status").filter({ hasText: "偏好已保存。" }).waitFor({ state: "visible", timeout: 20_000 });
        await page.reload();
        await page.getByLabel("回答长度").waitFor({ state: "visible" });
        assert.equal(await page.getByLabel("回答长度").inputValue(), savedBaseline.response_length);
        assert.equal(await page.getByLabel("讲解顺序").inputValue(), savedBaseline.example_order);
        const verified = await api(page, "/me/preferences");
        assert.equal(verified.status, 200);
        assert.deepEqual(verified.body.data.preferences, savedBaseline, "final preference state must equal baseline");
      } catch (error) {
        restoreError = error;
      }
    }
    await browser.close();
  }

  assert.deepEqual(businessWrites.filter((item) => !(item.method === "PATCH" && item.path === "/api/v1/me/preferences")), [],
    "only preference PATCH writes are allowed after login");
  assert.equal(businessWrites.length, 2, "only one preference update and one finally restoration PATCH are allowed");
  assert.deepEqual(pageErrors, [], "Growth/Preference should not produce browser errors");
  if (restoreError) throw new Error(`偏好基线恢复失败：${restoreError.message}`);
  console.log(JSON.stringify({
    growth_projection_verified: true,
    growth_review_count: true,
    cross_course_reviews_hidden: true,
    preference_refresh_persisted: true,
    preference_baseline_restored: true,
    preference_writes: businessWrites.length,
    out_of_scope_personal_reads_blocked: blockedPersonalReads.length,
    page_errors: pageErrors.length,
  }));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
