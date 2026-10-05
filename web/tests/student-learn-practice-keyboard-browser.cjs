/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const targetUrl = process.env.R3_UI_E2E_URL ?? "http://127.0.0.1:3002";
const email = process.env.R3_UI_E2E_EMAIL;
const password = process.env.R3_UI_E2E_PASSWORD;
const browserPath = process.env.R3_UI_E2E_BROWSER ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const viewports = [360, 393, 768];

if (!email || !password) {
  throw new Error("请通过 R3_UI_E2E_EMAIL 和 R3_UI_E2E_PASSWORD 提供隔离 synthetic 学生账号。");
}

function record(name, detail) {
  console.log(`PASS ${name}: ${detail}`);
}

async function focusSnapshot(page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement) || element === document.body) return null;
    const style = getComputedStyle(element);
    const label = element.getAttribute("aria-label")
      ?? (element.labels ? Array.from(element.labels).map((item) => item.innerText.trim()).join(" ") : "")
      ?? element.getAttribute("name")
      ?? element.innerText?.trim()
      ?? "";
    const text = element.innerText?.trim().replace(/\s+/g, " ").slice(0, 70) ?? "";
    const name = label || text || element.getAttribute("name") || element.getAttribute("href") || "";
    const href = element instanceof HTMLAnchorElement ? element.getAttribute("href") ?? "" : "";
    const key = `${element.tagName.toLowerCase()}|${element.id}|${element.getAttribute("name") ?? ""}|${href}|${name}`;
    const rect = element.getBoundingClientRect();
    return {
      key,
      name,
      tag: element.tagName.toLowerCase(),
      frameworkPortal: element.tagName.toLowerCase() === "nextjs-portal",
      focusVisible: element.matches(":focus-visible"),
      inViewport: rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth,
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      outlineColor: style.outlineColor,
      boxShadow: style.boxShadow,
    };
  });
}

async function traverse(page, direction) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });
  const steps = [];
  const key = direction === "forward" ? "Tab" : "Shift+Tab";
  for (let index = 0; index < 250; index += 1) {
    await page.keyboard.press(key);
    const focus = await focusSnapshot(page);
    if (!focus) break;
    // Next.js dev-mode portal is a framework control, not part of the student UI.
    if (focus.frameworkPortal) continue;
    if (steps.length > 0 && focus.key === steps[0].key) break;
    assert.equal(focus.focusVisible, true, `${direction} focus should match :focus-visible: ${JSON.stringify(focus)}`);
    assert.equal(focus.inViewport, true, `${direction} focus should remain visible in the viewport: ${JSON.stringify(focus)}`);
    const hasOutline = focus.outlineStyle !== "none"
      && focus.outlineWidth !== "0px"
      && focus.outlineColor !== "transparent"
      && !/rgba\([^)]*,\s*0(?:\.0+)?\)$/.test(focus.outlineColor);
    const hasShadow = focus.boxShadow !== "none" && !/rgba\([^)]*,\s*0(?:\.0+)?\)/.test(focus.boxShadow);
    assert.ok(hasOutline || hasShadow, `${direction} focus should have a visible indicator: ${JSON.stringify(focus)}`);
    steps.push(focus);
  }
  assert.ok(steps.length > 0, `${direction} traversal should reach interactive content`);
  return steps;
}

async function checkViewport(page, route, width) {
  await page.setViewportSize({ width, height: 844 });
  await page.goto(`${targetUrl}${route.path}`);
  await route.ready(page);
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  assert.ok(layout.content <= layout.viewport, `${route.name} overflows at ${width}px: ${JSON.stringify(layout)}`);
  const forward = await traverse(page, "forward");
  const reverse = await traverse(page, "reverse");
  assert.deepEqual(
    reverse.map((item) => item.key),
    forward.map((item) => item.key).reverse(),
    `${route.name} reverse traversal should retrace forward order at ${width}px\nforward=${JSON.stringify(forward.map((item) => item.name))}\nreverse=${JSON.stringify(reverse.map((item) => item.name))}`,
  );
  record(`${route.name} ${width}px`, `正向/反向各 ${forward.length} 个学生端焦点顺序一致，均有可见指示，无横向溢出`);
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 10 });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    await page.goto(`${targetUrl}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });
    await page.goto(`${targetUrl}/student`);
    await page.getByRole("heading", { name: "继续你的学习" }).waitFor({ state: "visible" });
    await page.waitForFunction(() => Array.from(document.querySelectorAll('a[href^="/student/courses/"]'))
      .some((anchor) => /^\/student\/courses\/[^/]+$/.test(anchor.getAttribute("href") ?? "")), null, { timeout: 20_000 });
    const coursePath = await page.locator('a[href^="/student/courses/"]').evaluateAll((anchors) => anchors
      .map((anchor) => anchor.getAttribute("href"))
      .find((href) => href && /^\/student\/courses\/[^/]+$/.test(href)));
    assert.ok(coursePath, "Home should expose an authorized course route");

    const routes = [
      {
        name: "Learn",
        path: `${coursePath}/learn`,
        ready: async (currentPage) => {
          await currentPage.getByRole("heading", { name: "学习", exact: true }).waitFor({ state: "visible" });
          await currentPage.locator("#course-search").waitFor({ state: "visible" });
          await currentPage.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
          await currentPage.waitForFunction(() => !Array.from(document.querySelectorAll(".status-banner"))
            .some((banner) => banner.textContent?.includes("正在读取可学习教材")));
        },
      },
      {
        name: "Practice",
        path: `${coursePath}/practice`,
        ready: async (currentPage) => {
          await currentPage.getByRole("heading", { name: "练习与复习", exact: true }).waitFor({ state: "visible" });
          await currentPage.getByRole("heading", { name: "可参加的练习", exact: true }).waitFor({ state: "visible" });
          await currentPage.waitForFunction(() => !Array.from(document.querySelectorAll(".status-banner"))
            .some((banner) => banner.textContent?.includes("正在读取练习") || banner.textContent?.includes("正在读取可用实验")));
        },
      },
    ];

    for (const width of viewports) {
      for (const route of routes) await checkViewport(page, route, width);
    }
    assert.deepEqual(errors, [], "Learn/Practice should not produce browser errors");
    record("Browser errors", "0 page errors across Learn and Practice at 360/393/768px");
    console.log("BLOCKED Reader: 当前 Learn 页面没有已保存引用卡片；搜索和新建 Tutor turn 均在任务限制内禁止");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
