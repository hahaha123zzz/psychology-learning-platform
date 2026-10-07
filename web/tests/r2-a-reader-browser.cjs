/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const targetUrl = process.env.R2A_E2E_URL ?? "http://127.0.0.1:3201";
const evidence = JSON.parse(process.env.R2A_E2E_SEED ?? "null");
const password = process.env.R2A_E2E_PASSWORD ?? "correct-password";
const browserPath = process.env.R2A_E2E_BROWSER ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const evidenceDirectory = process.env.R2A_EVIDENCE_DIR ?? path.resolve("tests/evidence/r2-a-reader");

if (!evidence?.course_id || !evidence?.evidence_pointer_id || !evidence?.student_id) {
  throw new Error("R2A_E2E_SEED 必须包含 course_id、student_id 和 evidence_pointer_id。");
}

const report = {
  target: targetUrl,
  course_id: evidence.course_id,
  material_version_id: evidence.material_version_id,
  seed_evidence_pointer_id: evidence.evidence_pointer_id,
  reader_pointer_id: null,
  checks: [],
  screenshots: [],
  requests: [],
};

function record(name, detail) {
  report.checks.push({ name, detail });
  console.log(`PASS ${name}: ${detail}`);
}

async function capture(page, name) {
  const file = path.join(evidenceDirectory, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  report.screenshots.push(file);
}

async function login(page, email) {
  await page.goto(`${targetUrl}/login`);
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });
}

async function searchReaderResult(page, courseId, materialVersionId) {
  await page.getByLabel("搜索课程资料").fill("independent variable validity");
  const searchResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith("/api/v1/knowledge/search") && response.request().method() === "POST";
  });
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  const searchPayload = await (await searchResponsePromise).json();
  const item = searchPayload.data.items.find(
    (candidate) =>
      candidate.material_version_id === materialVersionId &&
      candidate.evidence_pointer_id &&
      candidate.bbox,
  );
  assert.ok(item, "实际搜索响应应返回 E2E 固定资料版本的页内锚点。");
  const result = page.locator(".evidence-list article").filter({ hasText: item.text }).first();
  await result.waitFor({ state: "visible", timeout: 20_000 });
  return { item, result };
}

async function main() {
  fs.mkdirSync(evidenceDirectory, { recursive: true });
  const browser = await chromium.launch({
    executablePath: browserPath,
    headless: false,
    slowMo: 40,
  });
  const studentContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const studentPage = await studentContext.newPage();
  const pointerPrefix = "/api/v1/evidence-pointers/";

  studentPage.on("response", (response) => {
    const responseUrl = new URL(response.url());
    const pathname = responseUrl.pathname;
    if (pathname.includes(pointerPrefix)) {
      report.requests.push({ pathname, status: response.status() });
    }
  });

  try {
    await login(studentPage, evidence.student_email);
    await studentPage.goto(`${targetUrl}/student/courses/${evidence.course_id}/learn`);
    let current = await searchReaderResult(
      studentPage,
      evidence.course_id,
      evidence.material_version_id,
    );
    report.reader_pointer_id = current.item.evidence_pointer_id;
    let openedPointerPath = `${pointerPrefix}${current.item.evidence_pointer_id}`;
    let result = current.result;
    await result.getByRole("button", { name: "查看固定来源快照" }).click();

    const drawer = studentPage.getByRole("dialog", { name: "资料来源" });
    await drawer.waitFor({ state: "visible" });
    const pageImage = drawer.getByRole("img", { name: /资料物理页/ });
    await pageImage.waitFor({ state: "visible", timeout: 20_000 });
    const viewport = drawer.locator(".reader-image-viewport");
    const overlay = viewport.locator('span[aria-hidden="true"]');
    const imageBox = await pageImage.boundingBox();
    const overlayBox = await overlay.boundingBox();
    assert.ok(imageBox && overlayBox, "固定页图和定位框应在真实浏览器中可见");
    assert.ok(overlayBox.width > 0 && overlayBox.height > 0, "定位框必须有可见面积");
    assert.ok(overlayBox.x >= imageBox.x - 2 && overlayBox.y >= imageBox.y - 2);
    assert.ok(overlayBox.x + overlayBox.width <= imageBox.x + imageBox.width + 2);
    assert.ok(overlayBox.y + overlayBox.height <= imageBox.y + imageBox.height + 2);
    assert.match(await pageImage.getAttribute("alt"), /物理页/);
    await capture(studentPage, "01-reader-page-highlight");
    record(
      "已发布教材页图与锚点高亮",
      `浏览器显示物理页 ${evidence.physical_page}；定位框落在页图范围内。`,
    );

    const zoomIn = drawer.getByRole("button", { name: "放大页图" });
    await zoomIn.focus();
    await zoomIn.press("Enter");
    await drawer.getByText("125%", { exact: true }).waitFor();
    const rotateClockwise = drawer.getByRole("button", { name: "顺时针旋转页图" });
    await rotateClockwise.focus();
    await rotateClockwise.press("Enter");
    const rotationMatrix = await viewport.locator(".reader-image-stage > div").evaluate(
      (element) => {
        const matrix = new DOMMatrix(getComputedStyle(element).transform);
        return { b: matrix.b, c: matrix.c };
      },
    );
    assert.ok(Math.abs(rotationMatrix.b - 1) < 0.01 && Math.abs(rotationMatrix.c + 1) < 0.01);
    await capture(studentPage, "02-reader-zoom-rotation");
    record("键盘缩放和旋转", "使用焦点与 Enter 激活后，页图和高亮同层旋转 90°。");

    await studentPage.setViewportSize({ width: 390, height: 844 });
    await capture(studentPage, "03-reader-narrow-screen");
    const drawerBox = await drawer.boundingBox();
    assert.ok(drawerBox && drawerBox.width <= 390);
    await drawer.getByRole("button", { name: "关闭上下文面板" }).click();
    record("窄屏与关闭", "390px 视口内抽屉可见且可由可访问名称的关闭按钮关闭。");

    await studentPage.reload();
    await studentPage.getByLabel("搜索课程资料").waitFor({ state: "visible" });
    current = await searchReaderResult(
      studentPage,
      evidence.course_id,
      evidence.material_version_id,
    );
    report.reader_pointer_id = current.item.evidence_pointer_id;
    openedPointerPath = `${pointerPrefix}${current.item.evidence_pointer_id}`;
    result = current.result;
    await result.getByRole("button", { name: "查看固定来源快照" }).click();
    const refreshedDrawer = studentPage.getByRole("dialog", { name: "资料来源" });
    await refreshedDrawer.getByRole("img", { name: /资料物理页/ }).waitFor({ timeout: 20_000 });
    await capture(studentPage, "04-reader-refresh-restored");
    record("刷新后重新定位", "页面刷新并再次检索后，从已发布版本重新读取页图和锚点。");
    await refreshedDrawer.getByRole("button", { name: "关闭上下文面板" }).click();

    const teacherContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const teacherPage = await teacherContext.newPage();
    try {
      await login(teacherPage, evidence.teacher_email);
      const removal = await teacherPage.evaluate(
        async ({ courseId, membershipId }) => {
          const response = await fetch(`/api/v1/courses/${courseId}/members/${membershipId}`, {
            method: "DELETE",
            credentials: "include",
          });
          return { status: response.status, body: await response.json() };
        },
        { courseId: evidence.course_id, membershipId: evidence.membership_id },
      );
      assert.equal(removal.status, 200, JSON.stringify(removal.body));
    } finally {
      await teacherContext.close();
    }

    const revokedPointerResponse = studentPage.waitForResponse((response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        pathname.endsWith(openedPointerPath) &&
        response.status() === 404
      );
    }, { timeout: 10_000 });
    await result.getByRole("button", { name: "查看固定来源快照" }).click();
    const revokedResponse = await revokedPointerResponse;
    assert.equal(revokedResponse.status(), 404);
    await refreshedDrawer.getByText("课程不存在或无权访问", { exact: true }).waitFor({ timeout: 10_000 });
    await capture(studentPage, "05-reader-revoked-access");
    record("撤权后重新鉴权", "教师移除学生课程成员关系后，重新打开引用收到 404，未返回快照。");

    fs.writeFileSync(
      path.join(evidenceDirectory, "result.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
  } finally {
    await studentContext.close();
    await browser.close();
  }
}

main().catch((error) => {
  try {
    fs.mkdirSync(evidenceDirectory, { recursive: true });
    fs.writeFileSync(
      path.join(evidenceDirectory, "result.json"),
      `${JSON.stringify({ ...report, error: error.message }, null, 2)}\n`,
      "utf8",
    );
  } catch {
    // 保留浏览器错误作为主失败信息。
  }
  console.error(error);
  process.exitCode = 1;
});
