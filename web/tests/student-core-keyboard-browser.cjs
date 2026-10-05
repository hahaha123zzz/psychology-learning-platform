/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const targetUrl = process.env.R3_UI_E2E_URL ?? "http://localhost:3204";
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

async function waitForRoute(page, path) {
  await page.goto(`${targetUrl}${path}`);
  await page.waitForLoadState("domcontentloaded");
}

async function describeFocus(page) {
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
    return {
      key,
      name,
      tag: element.tagName.toLowerCase(),
      focusVisible: element.matches(":focus-visible"),
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
    const focus = await describeFocus(page);
    if (!focus) break;
    if (steps.length > 0 && focus.key === steps[0].key) break;
    assert.equal(focus.focusVisible, true, `${direction} focus should match :focus-visible: ${JSON.stringify(focus)}`);
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
  await waitForRoute(page, route.path);
  await route.ready(page);
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  assert.ok(layout.content <= layout.viewport, `${route.name} overflows at ${width}px: ${JSON.stringify(layout)}`);
  const forward = await traverse(page, "forward");
  const reverse = await traverse(page, "reverse");
  assert.deepEqual(reverse.map((item) => item.key), forward.map((item) => item.key).reverse(), `${route.name} reverse traversal should retrace forward order at ${width}px`);
  record(`${route.name} ${width}px`, `正向/反向各 ${forward.length} 个焦点顺序一致，所有焦点有可见指示，无横向溢出`);
  return forward;
}

async function checkGrowthTabs(page) {
  const tabs = page.getByRole("tab");
  assert.equal(await tabs.count(), 4, "成长页应有四个类别标签");
  assert.equal(await page.locator('[role="tab"][tabindex="0"]').count(), 1, "成长标签组应只有当前项可通过 Tab 聚焦");
  await page.getByRole("tab", { name: "知识", exact: true }).focus();
  for (const [key, label] of [["ArrowRight", "技能"], ["ArrowRight", "误区"], ["ArrowRight", "轨迹"], ["ArrowRight", "知识"], ["End", "轨迹"], ["Home", "知识"], ["ArrowLeft", "轨迹"]]) {
    await page.keyboard.press(key);
    const selected = page.getByRole("tab", { name: label, exact: true });
    await assert.doesNotReject(() => selected.waitFor({ state: "visible" }));
    assert.equal(await selected.getAttribute("aria-selected"), "true", `${key} should activate ${label}`);
    assert.equal(await selected.evaluate((element) => element === document.activeElement), true, `${key} should move focus to ${label}`);
  }
  const panelLabel = await page.getByRole("tabpanel").getAttribute("aria-labelledby");
  assert.equal(panelLabel, await page.locator('[role="tab"][aria-selected="true"]').getAttribute("id"), "tab panel should be labelled by the selected tab");
  record("Growth tab keys", "ArrowLeft/Right wraps and activates; Home/End reach endpoints; panel label follows selection");
}

async function main() {
  const browser = await chromium.launch({ executablePath: browserPath, headless: false, slowMo: 10 });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    await waitForRoute(page, "/login");
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
    const growthPath = `${coursePath}/growth`;
    const preferencePath = growthPath.replace(/\/growth$/, "/me");
    const routes = [
      { name: "Home", path: "/student", ready: async (currentPage) => {
        await currentPage.getByRole("heading", { name: "继续你的学习" }).waitFor({ state: "visible" });
        await currentPage.locator(".student-home-focus").waitFor({ state: "visible" });
        await currentPage.waitForFunction(() => document.querySelectorAll('a[href^="/student/courses/"]').length > 0, null, { timeout: 20_000 });
      } },
      { name: "Growth", path: growthPath, ready: (currentPage) => currentPage.getByRole("tablist", { name: "成长信息类别" }).waitFor({ state: "visible" }) },
      { name: "Preference", path: preferencePath, ready: (currentPage) => currentPage.locator("#hint-density").waitFor({ state: "visible" }) },
    ];

    for (const width of viewports) {
      for (const route of routes) {
        await checkViewport(page, route, width);
        if (route.name === "Growth") await checkGrowthTabs(page);
      }
    }
    assert.deepEqual(errors, [], "student core accessibility routes should not produce browser errors");
    record("Browser errors", "0 page errors across Home, Growth, Preference at 360/393/768px");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
