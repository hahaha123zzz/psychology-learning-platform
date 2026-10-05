import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webUrl = process.env.R3_G_WEB_URL ?? "http://127.0.0.1:3216";
const cdpPort = 9316;
const serverRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../server");
const snapshotName = process.env.R3_G_SNAPSHOT_NAME ?? "r3-g-mini-lab-20261005b";
const snapshotRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), `../.r3-runtime/${snapshotName}`);
const python = process.env.R3_G_PYTHON ?? path.join(serverRoot, ".venv", "Scripts", "python.exe");
const edge = process.env.R3_G_CHROME_EXE ?? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

const seed = JSON.parse(execFileSync(python, ["tests/r3_g_browser_seed.py"], {
  cwd: serverRoot,
  encoding: "utf8",
  env: {
    ...process.env,
    PSYCHOLOGY_TEST_DB: "psychology_learning_v1_r3_g_20261004",
    PSYCHOLOGY_TEST_REDIS_URL: "redis://127.0.0.1:6379/10",
    DATABASE_URL: "postgresql+asyncpg://psychology:change-me@127.0.0.1:5432/psychology_learning_v1_r3_g_20261004",
    REDIS_URL: "redis://127.0.0.1:6379/10",
    CELERY_BROKER_URL: "redis://127.0.0.1:6379/10",
    CELERY_RESULT_BACKEND: "redis://127.0.0.1:6379/10",
    MINIO_BUCKET: "v1-r3-g",
    PORT: "8216",
  },
}));

const teacher = await fetch(`${webUrl}/api/v1/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ email: seed.teacher_email, password: seed.password }),
});
assert.equal(teacher.status, 200, `teacher login should reach the G API proxy: ${await teacher.text()}`);
const teacherCookie = teacher.headers.getSetCookie().map((value) => value.split(";")[0]).join("; ");
const createCourse = await fetch(`${webUrl}/api/v1/courses`, {
  method: "POST",
  headers: { "content-type": "application/json", cookie: teacherCookie },
  body: JSON.stringify({ title: "R3-G Mini Lab browser verification", term: "2026秋", timezone: "Asia/Shanghai" }),
});
assert.equal(createCourse.status, 201);
const course = (await createCourse.json()).data;
const addStudent = await fetch(`${webUrl}/api/v1/courses/${course.id}/members`, {
  method: "POST",
  headers: { "content-type": "application/json", cookie: teacherCookie },
  body: JSON.stringify({ user_id: seed.student_id, role: "student" }),
});
assert.equal(addStudent.status, 201);

const browserProcess = spawn(edge, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-allow-origins=*",
  `--remote-debugging-port=${cdpPort}`,
  `--user-data-dir=${path.join(snapshotRoot, `.r3-g-edge-profile-${Date.now()}`)}`,
  "about:blank",
], { windowsHide: true, stdio: "ignore" });

let cdp;
try {
  const startedAt = Date.now();
  let targets;
  while (Date.now() - startedAt < 20_000) {
    try {
      targets = await (await fetch(`http://127.0.0.1:${cdpPort}/json/list`)).json();
      break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  assert.ok(targets?.length, "Edge CDP endpoint did not become ready");
  const target = targets.find((item) => item.type === "page");
  assert.ok(target?.webSocketDebuggerUrl, "Edge page target did not expose CDP");

  cdp = await new Promise((resolve, reject) => {
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    const pending = new Map();
    const listeners = new Map();
    let nextId = 1;
    socket.addEventListener("open", () => resolve({
      socket,
      on(method, callback) {
        const callbacks = listeners.get(method) ?? [];
        callbacks.push(callback);
        listeners.set(method, callbacks);
      },
      send(method, params = {}) {
        const id = nextId++;
        return new Promise((done, fail) => {
          pending.set(id, { done, fail });
          socket.send(JSON.stringify({ id, method, params }));
        });
      },
      close() { socket.close(); },
    }));
    socket.addEventListener("error", reject);
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        const current = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) current.fail(new Error(message.error.message));
        else current.done(message.result);
      } else if (message.method) {
        for (const callback of listeners.get(message.method) ?? []) void callback(message.params);
      }
    });
  });

  const evaluate = async (expression) => {
    const result = await cdp.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "browser evaluation failed");
    return result.result?.value;
  };
  const waitFor = async (expression, description, timeoutMs = 12_000) => {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (await evaluate(expression)) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const diagnostics = await evaluate(`JSON.stringify({path: location.pathname, title: document.title, text: document.body.innerText.slice(0, 3000), task: sessionStorage.getItem('student-learning-task')})`);
    throw new Error(`Timed out waiting for ${description}; browser state=${diagnostics}`);
  };
  const navigate = async (url) => {
    await cdp.send("Page.navigate", { url });
    await waitFor("document.readyState === 'complete'", `page load: ${url}`);
  };
  const clickButton = async (label) => {
    const clicked = await evaluate(`(() => {
      const button = [...document.querySelectorAll('button')].find((item) => item.innerText.trim() === ${JSON.stringify(label)});
      if (!button || button.disabled) return false;
      button.click();
      return true;
    })()`);
    assert.equal(clicked, true, `button not available: ${label}`);
  };
  const apiGet = (pathValue) => evaluate(`fetch(${JSON.stringify(`/api/v1${pathValue}`)}, { credentials: 'include' }).then((response) => response.json())`);

  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Network.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 375,
    height: 812,
    deviceScaleFactor: 1,
    mobile: true,
  });
  let failedFirstCheckpoint = false;
  const fallbackTaskId = "r3-g-a11y-fallback-fixture";
  await cdp.send("Fetch.enable", {
    patterns: [
      { urlPattern: "*/api/v1/student/labs/*/trials", requestStage: "Request" },
      { urlPattern: `*/api/v1/student/learning/tasks/${fallbackTaskId}`, requestStage: "Request" },
    ],
  });
  cdp.on("Fetch.requestPaused", async (event) => {
    if (event.request.url.endsWith(`/student/learning/tasks/${fallbackTaskId}`)) {
      const fixture = {
        id: fallbackTaskId,
        course_id: course.id,
        state: "explain",
        state_version: 1,
        tutor_message: "无障碍 fallback 浏览器工程 fixture。",
        hint_level: 1,
        status: "active",
        allowed_actions: ["RESPOND_TASK"],
        blocks: [
          {
            id: "r3-g-fallback-block",
            type: "TeachingAsset",
            template: "unsupported-template-fixture",
            content: {},
            fallback_text: "仅用于界面验收的纯文本说明，不代表正式心理学课程内容。",
          },
          {
            id: "r3-g-keyboard-asset-block",
            type: "TeachingAsset",
            template: "explanation",
            content: { title: "键盘 disclosure 工程 fixture", text: "此条只验证原生 details 控件的键盘行为。" },
            fallback_text: "受支持模板的附加纯文本说明。",
          },
        ],
      };
      const body = Buffer.from(JSON.stringify({
        data: fixture,
        meta: { request_id: "r3-g-browser-fixture", server_time: new Date().toISOString() },
      })).toString("base64");
      await cdp.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 200,
        responseHeaders: [{ name: "content-type", value: "application/json" }],
        body,
      });
    } else if (!failedFirstCheckpoint && event.request.url.includes("/student/labs/") && event.request.url.endsWith("/trials")) {
      failedFirstCheckpoint = true;
      await cdp.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "Failed" });
    } else {
      await cdp.send("Fetch.continueRequest", { requestId: event.requestId });
    }
  });
  let invalidationRequest = null;
  cdp.on("Network.requestWillBeSent", (event) => {
    if (event.request.url.endsWith("/invalidate") && event.request.postData) {
      invalidationRequest = JSON.parse(event.request.postData);
    }
  });

  await navigate(`${webUrl}/login`);
  await evaluate(`(() => {
    const fields = [...document.querySelectorAll('label')];
    const email = fields.find((item) => item.innerText.includes('邮箱'))?.querySelector('input');
    const password = fields.find((item) => item.innerText.includes('密码'))?.querySelector('input');
    const set = (input, value) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    };
    if (!email || !password) throw new Error('login fields not found');
    set(email, ${JSON.stringify(seed.student_email)});
    set(password, ${JSON.stringify(seed.password)});
    [...document.querySelectorAll('button')].find((item) => item.innerText.trim() === '登录')?.click();
    return true;
  })()`);
  await waitFor("location.pathname === '/student'", "student login redirect");
  await navigate(`${webUrl}/student/courses/${course.id}/practice`);
  await waitFor("document.body.innerText.includes('Mini Lab 实验学习')", "Mini Lab panel");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '开始 Mini Lab' && !item.disabled)", "available lab catalog");
  await clickButton("开始 Mini Lab");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '开始')", "intro trial");
  await clickButton("开始");
  await waitFor("document.body.innerText.includes('本次试次未保存：服务端未确认该答案，不会计入实验结果或资格化。')", "unconfirmed trial announcement");

  const narrowPanel = await evaluate(`(() => {
    const panel = document.querySelector('.mini-lab-panel');
    const reason = document.querySelector('#mini-lab-invalidation-reason');
    const invalidate = [...panel.querySelectorAll('button')].find((item) => item.innerText.trim() === '作废当前实验');
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(reason, '窄屏键盘验收后继续本次工程 fixture');
    reason.dispatchEvent(new Event('input', { bubbles: true }));
    reason.dispatchEvent(new Event('change', { bubbles: true }));
    reason.focus();
    return {
      viewportWidth: window.innerWidth,
      panelWidth: panel.clientWidth,
      panelScrollWidth: panel.scrollWidth,
      reasonWidth: reason.getBoundingClientRect().width,
      invalidateDisabled: invalidate.disabled,
    };
  })()`);
  assert.equal(narrowPanel.viewportWidth, 375);
  assert.ok(narrowPanel.panelScrollWidth <= narrowPanel.panelWidth, `Mini Lab panel overflows at 375px: ${JSON.stringify(narrowPanel)}`);
  assert.ok(narrowPanel.reasonWidth > 0);
  assert.equal(narrowPanel.invalidateDisabled, false);
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
  const keyboardFocus = await evaluate(`(() => {
    const active = document.activeElement;
    return {
      label: active?.innerText?.trim(),
      id: active?.id,
      outlineWidth: getComputedStyle(active).outlineWidth,
      outlineStyle: getComputedStyle(active).outlineStyle,
    };
  })()`);
  assert.equal(keyboardFocus.label, "作废当前实验", `Tab should move from the reason to the invalidate button: ${JSON.stringify(keyboardFocus)}`);
  assert.equal(keyboardFocus.outlineWidth, "2px");
  assert.equal(keyboardFocus.outlineStyle, "solid");
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", modifiers: 8, windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", modifiers: 8, windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
  assert.equal(await evaluate("document.activeElement.id"), "mini-lab-invalidation-reason", "Shift+Tab should return focus to the reason");

  let activeResponse = await apiGet(`/student/labs/active?course_id=${course.id}`);
  let session = activeResponse.data;
  assert.equal(session.trial_data.length, 0, "the request aborted in the browser must not persist");
  await clickButton("恢复已保存阶段");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '开始')", "recovered intro trial");
  await clickButton("开始");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '有线索条件')", "prediction trial");
  activeResponse = await apiGet(`/student/labs/active?course_id=${course.id}`);
  session = activeResponse.data;
  assert.equal(session.trial_data.length, 1);
  assert.equal(session.trial_data[0].phase, "intro");

  await cdp.send("Page.reload", { ignoreCache: true });
  await waitFor("[...document.querySelectorAll('h2')].some((item) => item.innerText.trim() === '先做预测')", "refresh-restored prediction phase");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '有线索条件' && !item.disabled)", "enabled restored prediction action");
  await clickButton("有线索条件");
  await waitFor("[...document.querySelectorAll('button')].some((item) => item.innerText.trim() === '线索条件更快')", "run trial after saved prediction");

  await evaluate(`(() => {
    const textarea = document.querySelector('#mini-lab-invalidation-reason');
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(textarea, '浏览器中断后主动结束工程验证会话');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
  await waitFor("!document.querySelector('button')?.disabled", "enabled invalidation action");
  await clickButton("作废当前实验");
  await waitFor("document.body.innerText.includes('实验已作废')", "invalidated terminal state");
  assert.equal(await evaluate("document.querySelectorAll('.mini-lab-runtime').length"), 0);
  assert.ok(invalidationRequest?.idempotency_key, "invalidation should include an idempotency key");
  const replay = await evaluate(`fetch(${JSON.stringify(`/api/v1/student/labs/${session.id}/invalidate`)}, {
    method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(${JSON.stringify(invalidationRequest)})
  }).then(async (response) => ({ status: response.status, body: await response.json() }))`);
  assert.equal(replay.status, 200);
  assert.equal(replay.body.data.status, "invalidated");
  const cannotResume = await evaluate(`fetch(${JSON.stringify(`/api/v1/student/labs/${session.id}/trials`)}, {
    method: 'POST', credentials: 'include', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ version: ${invalidationRequest.expected_version + 1}, trial_data: ${JSON.stringify([...session.trial_data, { phase: "predict", response: 0, rt: 100, recorded_at: new Date().toISOString() }])} })
  }).then(async (response) => ({ status: response.status, body: await response.json() }))`);
  assert.equal(cannotResume.status, 409);
  assert.equal(cannotResume.body.error.code, "MINI_LAB_INVALID_STATE");

  await evaluate(`sessionStorage.setItem('student-learning-task', ${JSON.stringify(fallbackTaskId)})`);
  await navigate(`${webUrl}/student/learning`);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 393,
    height: 812,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await waitFor("document.body.innerText.includes('教学资产降级为文字')", "TeachingAsset fallback fixture");
  const fallbackState = await evaluate(`(() => {
    const fallback = document.querySelector('.teaching-asset-fallback');
    const disclosure = document.querySelector('.teaching-asset-text-fallback');
    const summary = disclosure?.querySelector('summary');
    return {
      viewportWidth: window.innerWidth,
      reason: fallback?.dataset.fallbackReason,
      statusRole: fallback?.querySelector('[role="status"]')?.getAttribute('role'),
      scrollWidth: fallback?.scrollWidth,
      clientWidth: fallback?.clientWidth,
      summaryText: summary?.innerText,
      detailsWidth: disclosure?.scrollWidth,
      detailsClientWidth: disclosure?.clientWidth,
    };
  })()`);
  assert.equal(fallbackState.reason, "template_unsupported");
  assert.equal(fallbackState.statusRole, "status");
  assert.equal(fallbackState.viewportWidth, 393);
  assert.ok(fallbackState.scrollWidth <= fallbackState.clientWidth, `fallback overflows at 375px: ${JSON.stringify(fallbackState)}`);
  assert.ok(fallbackState.detailsWidth <= fallbackState.detailsClientWidth, `asset disclosure overflows at 375px: ${JSON.stringify(fallbackState)}`);
  assert.equal(fallbackState.summaryText, "展开纯文本说明");
  await evaluate("document.querySelector('.teaching-asset-text-fallback summary').focus()");
  assert.equal(
    await evaluate("document.activeElement === document.querySelector('.teaching-asset-text-fallback summary')"),
    true,
    "the asset disclosure summary should receive focus",
  );
  for (const [key, code, virtualKeyCode] of [["Enter", "Enter", 13], [" ", "Space", 32]]) {
    const text = key === "Enter" ? "\r" : key;
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key, code, text, unmodifiedText: text, windowsVirtualKeyCode: virtualKeyCode, nativeVirtualKeyCode: virtualKeyCode });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: virtualKeyCode, nativeVirtualKeyCode: virtualKeyCode });
    const isOpen = await evaluate("document.querySelector('.teaching-asset-text-fallback').open");
    assert.equal(isOpen, key === "Enter", `${code} should toggle the native details disclosure`);
  }

  const narrowMetrics = await evaluate(`(() => {
    const header = document.querySelector('.app-header');
    const fallback = document.querySelector('.teaching-asset-fallback');
    return {
      viewportWidth: window.innerWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      headerClientWidth: header?.clientWidth,
      headerScrollWidth: header?.scrollWidth,
      miniLabPanelClientWidth: document.querySelector('.mini-lab-panel')?.clientWidth,
      miniLabPanelScrollWidth: document.querySelector('.mini-lab-panel')?.scrollWidth,
      fallbackClientWidth: fallback?.clientWidth,
      fallbackScrollWidth: fallback?.scrollWidth,
    };
  })()`);
  assert.equal(narrowMetrics.viewportWidth, 393);
  const screenshot = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  const evidenceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "r3-g-evidence");
  fs.mkdirSync(evidenceDirectory, { recursive: true });
  const screenshotName = process.env.R3_G_SCREENSHOT_NAME ?? "mini-lab-a11y-393px-20261005.png";
  fs.writeFileSync(path.join(evidenceDirectory, screenshotName), Buffer.from(screenshot.data, "base64"));
  console.log(JSON.stringify({
    status: "passed",
    courseId: course.id,
    sessionId: session.id,
    scenarios: ["unconfirmed trial", "service checkpoint recovery", "refresh restore", "invalidation", "idempotent replay", "terminal resume rejection", "375px Mini Lab layout", "Tab/Shift+Tab focus and visible outline", "TeachingAsset fallback at 393px", "Enter/Space disclosure"],
    narrowMetrics,
    screenshot: `tests/r3-g-evidence/${screenshotName}`,
  }));
} finally {
  cdp?.close();
  browserProcess.kill();
}
