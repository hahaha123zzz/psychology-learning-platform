/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const TARGET_URL = process.env.R2B_E2E_URL ?? "http://127.0.0.1:3202";
const ADMIN_EMAIL = process.env.R2B_E2E_EMAIL;
const IAM_TARGET_EMAIL = process.env.R2B_E2E_IAM_TARGET_EMAIL;
const TEST_PASSWORD = process.env.R2B_E2E_PASSWORD;
const LEARNER_EMAIL = process.env.R2B_E2E_LEARNER_EMAIL;
const COURSE_MEMBER_EMAIL = process.env.R2B_E2E_COURSE_MEMBER_EMAIL;
const BROWSER_EXECUTABLE = process.env.R2B_E2E_BROWSER ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const EVIDENCE_DIR = process.env.R2B_EVIDENCE_DIR ?? path.resolve("tests/evidence/r2-b-governance");

if (!ADMIN_EMAIL || !IAM_TARGET_EMAIL || !TEST_PASSWORD || !LEARNER_EMAIL || !COURSE_MEMBER_EMAIL) {
  throw new Error("请通过 R2B_E2E_EMAIL、R2B_E2E_IAM_TARGET_EMAIL、R2B_E2E_PASSWORD、R2B_E2E_LEARNER_EMAIL 和 R2B_E2E_COURSE_MEMBER_EMAIL 提供隔离验收账号。");
}

const report = { target: TARGET_URL, checks: [], screenshots: [], expectedHttpFailures: [] };

function record(name, detail) {
  report.checks.push({ name, detail });
  console.log(`PASS ${name}: ${detail}`);
}

async function screenshot(page, name) {
  const filePath = path.join(EVIDENCE_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  report.screenshots.push(filePath);
}

async function screenshotElement(locator, name) {
  const filePath = path.join(EVIDENCE_DIR, `${name}.png`);
  await locator.screenshot({ path: filePath });
  report.screenshots.push(filePath);
}

async function login(page, email) {
  await page.goto(`${TARGET_URL}/login`);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(TEST_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL((url) => url.pathname !== "/login", { timeout: 15_000 });
}

async function openTab(page, name) {
  await page.getByRole("tab", { name: new RegExp(name) }).click();
}

async function confirmDialog(page, buttonName) {
  const dialog = page.getByRole("dialog");
  await dialog.waitFor({ state: "visible" });
  await dialog.getByRole("button", { name: buttonName, exact: true }).click();
  await dialog.waitFor({ state: "hidden", timeout: 15_000 });
}

async function selectTarget(page, searchLabel, selectLabel, email, index = 0) {
  const search = page.getByLabel(searchLabel).nth(index);
  await search.fill(email);
  const select = page.getByLabel(selectLabel).nth(index);
  await select.locator("option").filter({ hasText: email }).waitFor({ state: "attached" });
  const optionValue = await select.locator("option").filter({ hasText: email }).getAttribute("value");
  assert.ok(optionValue, `未找到同机构账号 ${email}`);
  await select.selectOption(optionValue);
}

async function main() {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const browser = await chromium.launch({ executablePath: BROWSER_EXECUTABLE, headless: false, slowMo: 60 });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/admin/") && response.status() >= 400) {
      report.expectedHttpFailures.push({ path: new URL(response.url()).pathname, status: response.status() });
    }
  });

  try {
    await login(page, ADMIN_EMAIL);
    await page.goto(`${TARGET_URL}/admin`);
    await page.getByText("管理员治理工作台", { exact: true }).waitFor({ state: "visible" });
    await page.getByText("同机构账号", { exact: true }).waitFor({ state: "visible" });
    await page.getByText("进行中测评", { exact: true }).waitFor({ state: "visible" });
    await screenshot(page, "01-overview-live");
    record("管理员概览实时数据", "真实登录后显示 health readiness、同机构账号数和进行中测评数");

    let releaseDelayedOverview;
    let delayNextOverview = false;
    await page.route("**/api/v1/admin/health", async (route) => {
      if (delayNextOverview) {
        delayNextOverview = false;
        await new Promise((resolve) => { releaseDelayedOverview = resolve; });
      }
      await route.continue();
    });
    delayNextOverview = true;
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    await page.getByRole("status").filter({ hasText: "正在读取管理员运行概览" }).waitFor({ state: "visible" });
    await screenshot(page, "02-overview-loading");
    releaseDelayedOverview();
    await page.getByText("同机构账号", { exact: true }).waitFor({ state: "visible" });
    record("概览 loading", "延迟真实 admin health 响应期间页面显示读取状态");

    let failNextOverview = false;
    await page.unroute("**/api/v1/admin/health");
    await page.route("**/api/v1/admin/health", async (route) => {
      if (failNextOverview) {
        failNextOverview = false;
        await route.abort("failed");
        return;
      }
      await route.continue();
    });
    failNextOverview = true;
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "无法读取管理员运行概览" }).waitFor({ state: "visible" });
    await screenshot(page, "03-overview-error");
    await page.getByRole("button", { name: "重试", exact: true }).click();
    await page.getByText("同机构账号", { exact: true }).waitFor({ state: "visible" });
    record("概览失败与重试", "浏览器中断一次真实代理请求，页面报告失败，随后从实际 API 重试恢复");
    await page.unroute("**/api/v1/admin/health");

    const apiDenied = await page.evaluate(async () => (await fetch("/api/v1/admin/health")).status);
    assert.equal(apiDenied, 200, "已登录管理员应能读取管理员概览");
    const courseId = process.env.R2B_E2E_COURSE_ID;
    const foreignCourseId = process.env.R2B_E2E_FOREIGN_COURSE_ID;
    assert.ok(courseId && foreignCourseId, "缺少隔离验收课程 ID");
    const courseContentStatus = await page.evaluate(async (id) => (await fetch(`/api/v1/courses/${id}`)).status, courseId);
    assert.equal(courseContentStatus, 404, "平台管理员不可因此获得课程教学资料读取权");
    const foreignStatus = await page.evaluate(async (id) => (await fetch(`/api/v1/admin/courses/${id}/classes`)).status, foreignCourseId);
    assert.equal(foreignStatus, 404, "跨机构课程必须不可枚举");
    record("管理员读取边界", "同一真实会话下教学课程详情和跨机构班级列表均返回 404");

    await page.setViewportSize({ width: 390, height: 844 });
    await openTab(page, "课程与班级");
    await page.locator("#admin-panel-classes").getByText(/窄屏只读：创建班级/).waitFor({ state: "visible" });
    assert.equal(await page.getByRole("heading", { name: "创建班级" }).count(), 0);
    await screenshot(page, "04-course-narrow-readonly");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.waitForTimeout(250);
    record("窄屏只读门禁", "移动视口仍可读，创建班级写入口被隐藏");

    await openTab(page, "IAM 授权");
    const raceContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const racePage = await raceContext.newPage();
    await login(racePage, ADMIN_EMAIL);
    await racePage.goto(`${TARGET_URL}/admin`);
    await racePage.getByText("管理员治理工作台", { exact: true }).waitFor({ state: "visible" });
    await openTab(racePage, "IAM 授权");
    const raceName = "R2-B 并发撤权对象";
    const primaryRaceCard = page.locator("article.question-card").filter({ hasText: raceName });
    const secondRaceCard = racePage.locator("article.question-card").filter({ hasText: raceName });
    await primaryRaceCard.getByText("撤销授权", { exact: true }).click();
    await primaryRaceCard.locator("textarea").fill("并发测试先提交撤销操作");
    await primaryRaceCard.getByRole("button", { name: "复核后撤销" }).click();
    await confirmDialog(page, "确认撤销");
    await page.getByRole("status").filter({ hasText: "授权已撤销" }).waitFor({ state: "visible" });
    await secondRaceCard.getByText("撤销授权", { exact: true }).click();
    await secondRaceCard.locator("textarea").fill("使用旧页面版本提交第二次撤销");
    await secondRaceCard.getByRole("button", { name: "复核后撤销" }).click();
    await confirmDialog(racePage, "确认撤销");
    await racePage.getByRole("alert").filter({ hasText: "409" }).waitFor({ state: "visible" });
    report.expectedHttpFailures.push({ path: "/api/v1/admin/role-assignments/{id}/revoke", status: 409 });
    await screenshot(racePage, "05-iam-version-conflict");
    record("IAM 409 乐观锁", "两个真实浏览器会话基于同一版本竞争撤权，第二次请求返回 409 并刷新列表");

    await page.getByLabel("查找同机构账号（姓名或邮箱至少 3 个字符）").fill(IAM_TARGET_EMAIL);
    const targetSelect = page.getByLabel("授权对象");
    await targetSelect.locator("option").filter({ hasText: IAM_TARGET_EMAIL }).waitFor({ state: "attached" });
    const grantTarget = await targetSelect.locator("option").filter({ hasText: IAM_TARGET_EMAIL }).getAttribute("value");
    assert.ok(grantTarget);
    await targetSelect.selectOption(grantTarget);
    await page.getByLabel("授权范围").selectOption("platform");
    await page.locator("#admin-panel-iam").getByLabel("角色").selectOption("assistant");
    await page.getByLabel("授权理由（必填，至少 8 个字符）").fill("浏览器验收平台助教授权流程");
    await page.getByRole("button", { name: "检查并复核授权" }).click();
    await page.getByRole("dialog").getByText("平台工作区", { exact: false }).waitFor({ state: "visible" });
    await page.getByRole("dialog").getByText(IAM_TARGET_EMAIL, { exact: false }).waitFor({ state: "visible" });
    await screenshotElement(page.getByRole("dialog"), "06-iam-confirmation");
    await confirmDialog(page, "确认授予");
    await page.getByRole("status").filter({ hasText: "授权已生效" }).waitFor({ state: "visible" });
    record("IAM 授予回执", "同机构对象、平台 Scope、角色和理由经复核后通过真实 API 授予并收到回执");

    await openTab(page, "课程与班级");
    await page.getByRole("heading", { name: "课程、班级与成员治理" }).waitFor({ state: "visible" });
    await page.getByRole("heading", { name: "创建班级" }).waitFor({ state: "visible" });
    const runSuffix = Date.now().toString(36).slice(-5).toUpperCase();
    const classCode = `B-${runSuffix}`;
    const className = `浏览器验收班级-${runSuffix}`;
    await page.getByLabel("班级代码").fill(classCode);
    await page.getByLabel("班级名称").fill(className);
    await page.getByLabel("创建理由（至少 8 个字符）").fill("新增浏览器端验收班级");
    await page.getByRole("button", { name: "复核并创建班级" }).click();
    await page.getByRole("dialog").getByText(classCode, { exact: false }).waitFor({ state: "visible" });
    await confirmDialog(page, "确认创建");
    await page.getByRole("status").filter({ hasText: "班级已创建" }).waitFor({ state: "visible" });

    const courseSearch = page.getByLabel("搜索同机构候选账号").nth(0);
    await courseSearch.fill(COURSE_MEMBER_EMAIL);
    const courseTargetSelect = page.getByLabel("待选账号").nth(0);
    await courseTargetSelect.locator("option").filter({ hasText: COURSE_MEMBER_EMAIL }).waitFor({ state: "attached" });
    const learnerId = await courseTargetSelect.locator("option").filter({ hasText: COURSE_MEMBER_EMAIL }).getAttribute("value");
    assert.ok(learnerId);
    await courseTargetSelect.selectOption(learnerId);
    await page.getByLabel("加入理由（至少 8 个字符）").fill("确认本学期加入课程成员");
    await page.getByRole("button", { name: "复核并加入课程" }).click();
    await page.getByRole("dialog").getByText(COURSE_MEMBER_EMAIL, { exact: false }).waitFor({ state: "visible" });
    await confirmDialog(page, "确认加入");
    await page.getByRole("status").filter({ hasText: "课程成员已加入" }).waitFor({ state: "visible" });

    const newClassCard = page.locator("article.question-card").filter({ hasText: `${classCode} · ${className}` });
    await newClassCard.getByRole("button", { name: "管理班级成员" }).click();
    await page.getByRole("heading", { name: "加入班级学生" }).waitFor({ state: "visible" });
    await selectTarget(page, "搜索同机构候选账号", "待选账号", COURSE_MEMBER_EMAIL, 1);
    await page.getByLabel("加入理由（至少 8 个字符）").nth(1).fill("将课程学生编入对应班级");
    await page.getByRole("button", { name: "复核并加入班级" }).click();
    await page.getByRole("dialog").getByText(className, { exact: false }).waitFor({ state: "visible" });
    await confirmDialog(page, "确认加入");
    await page.getByRole("status").filter({ hasText: "班级成员已加入" }).waitFor({ state: "visible" });

    const assignmentForm = page.getByRole("button", { name: "检查并复核分配" }).locator("xpath=..");
    const assignmentSelects = assignmentForm.locator("select");
    assert.equal(await assignmentSelects.count(), 3, "任课表单应依次提供班级、教师和职责选择框");
    await assignmentSelects.nth(0).selectOption({ label: `${classCode} · ${className}` });
    const teacherSelect = assignmentSelects.nth(1);
    const teacherOption = teacherSelect.locator("option").filter({ hasText: "R2-B 任课教师" });
    await teacherOption.waitFor({ state: "attached" });
    const teacherId = await teacherOption.getAttribute("value");
    assert.ok(teacherId, "未找到有效的课程教师候选项");
    await teacherSelect.selectOption(teacherId);
    await page.getByLabel("分配理由（必填，至少 8 个字符）").fill("为新建验收班级分配任课教师");
    await page.getByRole("button", { name: "检查并复核分配" }).click();
    await page.getByRole("dialog").getByText("主负责人", { exact: false }).waitFor({ state: "visible" });
    await confirmDialog(page, "确认分配");
    await page.getByRole("status").filter({ hasText: "任课关系已生效" }).waitFor({ state: "visible" });
    await screenshot(page, "07-course-class-membership");
    record("课程、班级与任课治理", "真实 API 创建班级、加入课程学生、加入班级学生并分配已入课教师，理由和确认对话框均已执行");

    await openTab(page, "任务恢复");
    await page.getByRole("heading", { name: "教材任务与恢复" }).waitFor({ state: "visible" });
    const failedJob = page.locator("article.question-card").filter({ hasText: "任务 " }).filter({ hasText: "失败" });
    await failedJob.getByText("受控重试", { exact: true }).click();
    await failedJob.locator("textarea").fill("浏览器验收重试失败解析任务");
    await failedJob.getByRole("button", { name: "复核后重试" }).click();
    await page.getByRole("dialog").getByText("尝试 1/5", { exact: false }).waitFor({ state: "visible" });
    await screenshotElement(page.getByRole("dialog"), "08-job-retry-confirmation");
    await confirmDialog(page, "确认重新排队");
    await page.getByRole("status").filter({ hasText: "任务已重新排队" }).waitFor({ state: "visible" });
    await page.getByText(/教材解析 · 排队中/).waitFor({ state: "visible" });
    await page.getByRole("combobox", { name: "状态" }).selectOption("succeeded");
    await page.getByText("当前筛选下没有同机构教材任务").waitFor({ state: "visible" });
    await screenshot(page, "09-job-empty-state");
    record("任务版本与受控恢复", "使用当前失败任务版本、理由和确认完成重试；任务转入队列，其他状态筛选展示真实空态");

    await openTab(page, "审计日志");
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    await page.getByText("admin.course_class.created", { exact: true }).first().waitFor({ state: "visible" });
    await page.getByText("admin.job.retry_requested", { exact: true }).first().waitFor({ state: "visible" });
    await screenshot(page, "10-audit-real-events");
    await page.getByLabel("操作类型（精确筛选）").fill("r2-b-no-such-operation");
    await page.getByRole("button", { name: "应用筛选" }).click();
    await page.getByText("当前机构范围和筛选条件下没有审计记录").waitFor({ state: "visible" });
    await screenshot(page, "11-audit-empty-state");
    record("审计过滤与无数据状态", "真实审计 API 包含前序治理操作；按不匹配操作精确筛选后显示无数据状态");

    const deniedContext = await browser.newContext();
    const deniedPage = await deniedContext.newPage();
    await login(deniedPage, LEARNER_EMAIL);
    const nonAdminStatus = await deniedPage.evaluate(async () => (await fetch("/api/v1/admin/health")).status);
    assert.equal(nonAdminStatus, 403, "非管理员直接请求管理 API 必须被服务端拒绝");
    report.expectedHttpFailures.push({ path: "/api/v1/admin/health", status: nonAdminStatus });
    record("非管理员服务端权限回归", "学生会话直接请求 /admin/health 得到 HTTP 403");
    await deniedContext.close();

    assert.deepEqual(errors, [], `浏览器运行时错误：${errors.join("; ")}`);
    await fs.promises.writeFile(path.join(EVIDENCE_DIR, "result.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
    console.log(`EVIDENCE ${path.join(EVIDENCE_DIR, "result.json")}`);
  } finally {
    await context.close();
    await browser.close();
  }
}

(async () => {
  try {
    await main();
  } catch (error) {
    console.error(error?.stack ?? String(error));
    try {
      fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
      fs.writeFileSync(path.join(EVIDENCE_DIR, "failure.json"), JSON.stringify({ ...report, failure: error?.stack ?? String(error) }, null, 2));
    } catch { /* 保留原始浏览器错误 */ }
    process.exitCode = 1;
  }
})();
