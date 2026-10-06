/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const webOrigin = process.env.UI012_WEB_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI012_STUDENT_EMAIL;
const password = process.env.UI012_STUDENT_PASSWORD;
const courseId = process.env.UI012_COURSE_ID;
const sessionId = process.env.UI012_SESSION_ID;
const query = process.env.UI012_QUERY;
const browserPath = process.env.UI012_CHROME_PATH;

if (!email || !password || !courseId || !sessionId || !query) {
  throw new Error("请使用环境变量提供现存 synthetic course_qa session、课程和查询词；本脚本不会创建会话或提交 Tutor 回合。");
}

const pins = {
  publication_snapshot_id: "01M00000000000000000000011",
  index_job_id: "01M00000000000000000000012",
  domain_release_id: "01M00000000000000000000013",
};
const ids = {
  caption: "01M00000000000000000000021",
  explains: "01M00000000000000000000022",
  figure: "01M00000000000000000000023",
};
const excerpts = {
  caption: "Synthetic approved caption context.",
  explains: "Synthetic approved explanation context.",
};
const pointer = (id, objectType, excerpt, sourceObjectId) => ({
  evidence_pointer_id: id,
  course_id: courseId,
  material_title: "合成练习教材",
  material_id: "01M00000000000000000000031",
  material_version_id: "01M00000000000000000000032",
  ...pins,
  source_object_id: sourceObjectId,
  chapter_path: "合成章节 / 图文关系",
  physical_page: 1,
  object_type: objectType,
  coordinate_space: "unavailable",
  bbox: null,
  anchors: [],
  excerpt,
  excerpt_sha256: "synthetic-only",
});
const envelope = (data) => ({
  data,
  meta: { request_id: "ui012-synthetic-harness", server_time: new Date().toISOString() },
});

function searchItems(noPinnedPointers) {
  const base = {
    evidence_id: "01M00000000000000000000041",
    evidence_pointer_id: null,
    material_id: "01M00000000000000000000031",
    material_version_id: "01M00000000000000000000032",
    title: "合成表格结果",
    text: "Synthetic search hit.",
    physical_page: 1,
    object_type: "table",
  };
  if (noPinnedPointers) {
    return [{
      ...base,
      closure: [
        { object_id: "ui012-no-pin-caption", object_type: "paragraph", relation_type: "caption_of", physical_page: 1, publication_snapshot_id: null },
        { object_id: "ui012-no-id-explanation", object_type: "paragraph", relation_type: "explains", physical_page: 1 },
        { object_id: "ui012-wrong-relation", object_type: "paragraph", relation_type: "next", evidence_pointer_id: "01M00000000000000000000051" },
        { object_id: "ui012-wrong-object", object_type: "figure", relation_type: "explains", evidence_pointer_id: "01M00000000000000000000052" },
      ],
    }];
  }
  return [{
    ...base,
    closure: [
      { object_id: "ui012-caption-object", object_type: "paragraph", relation_type: "caption_of", text: excerpts.caption, physical_page: 1, evidence_pointer_id: ids.caption },
      { object_id: "ui012-explains-object", object_type: "paragraph", relation_type: "explains", text: excerpts.explains, physical_page: 1, evidence_pointer_id: ids.explains },
      { object_id: "ui012-neighbor-figure", object_type: "figure", relation_type: "next", physical_page: 1, evidence_pointer_id: ids.figure },
      { object_id: "ui012-unapproved-relation", object_type: "paragraph", relation_type: "references", physical_page: 1, evidence_pointer_id: "01M00000000000000000000053" },
    ],
  }];
}

async function main() {
  const browser = await chromium.launch({ headless: true, ...(browserPath ? { executablePath: browserPath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  const writes = [];
  const pointerReads = [];
  const pageErrors = [];
  let noPinnedPointers = false;
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.goto(`${webOrigin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname !== "/login", { timeout: 20_000 });

    page.on("request", (request) => {
      if (["GET", "HEAD", "OPTIONS"].includes(request.method())) return;
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/v1/")) writes.push({ method: request.method(), path: url.pathname });
    });
    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (url.pathname.startsWith("/api/v1/evidence-pointers/") && response.request().method() === "GET") {
        try { pointerReads.push((await response.json()).data); } catch { pointerReads.push(null); }
      }
    });

    const session = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/chat/sessions/${encodeURIComponent(id)}`, { credentials: "include" });
      return { status: response.status, body: await response.json() };
    }, sessionId);
    assert.equal(session.status, 200);
    assert.equal(session.body.data.id, sessionId);
    assert.equal(session.body.data.course_id, courseId);
    assert.equal(session.body.data.mode, "course_qa");
    assert.equal(session.body.data.status, "active");

    await page.route("**/api/v1/knowledge/search", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ items: searchItems(noPinnedPointers) })) });
    });
    for (const id of Object.values(ids)) {
      const sourceObjectId = id === ids.caption ? "ui012-caption-object" : id === ids.explains ? "ui012-explains-object" : "ui012-neighbor-figure";
      const excerpt = id === ids.caption ? excerpts.caption : id === ids.explains ? excerpts.explains : "";
      const type = id === ids.figure ? "figure" : "paragraph";
      await page.route(`**/api/v1/evidence-pointers/${id}`, async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope(pointer(id, type, excerpt, sourceObjectId))) });
      });
    }

    await page.goto(`${webOrigin}/student/courses/${encodeURIComponent(courseId)}/learn?session_id=${encodeURIComponent(sessionId)}`);
    await page.getByRole("heading", { name: "学习助手", exact: true }).waitFor({ state: "visible" });
    await page.getByLabel("搜索教材").fill(query);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    const resultCards = page.locator(".evidence-list article");
    await resultCards.first().waitFor({ state: "visible", timeout: 20_000 });
    assert.equal(await resultCards.count(), 1, "context pointers must stay under the single search hit");
    assert.equal(await page.getByRole("button", { name: "查看图注来源", exact: true }).count(), 1);
    assert.equal(await page.getByRole("button", { name: "查看相邻段落来源", exact: true }).count(), 1);
    assert.equal(await page.getByRole("button", { name: /references|未固定|未绑定/ }).count(), 0);
    await page.getByText("图注上下文（非独立检索命中）", { exact: false }).waitFor({ state: "visible" });
    await page.getByText("解释段落上下文（非独立检索命中）", { exact: false }).waitFor({ state: "visible" });

    const turnCount = await page.locator(".learn-turn").count();
    const tableExplainCount = await page.locator(".table-explain-label").count();
    for (const [label, id, expectedExcerpt, expectedSource] of [
      ["查看图注来源", ids.caption, excerpts.caption, "ui012-caption-object"],
      ["查看相邻段落来源", ids.explains, excerpts.explains, "ui012-explains-object"],
    ]) {
      const responsePromise = page.waitForResponse((response) =>
        new URL(response.url()).pathname === `/api/v1/evidence-pointers/${id}` && response.request().method() === "GET",
      );
      await page.getByRole("button", { name: label, exact: true }).click();
      const response = await responsePromise;
      assert.equal(response.status(), 200);
      const drawer = page.getByRole("dialog", { name: "教材来源快照" });
      await drawer.waitFor({ state: "visible", timeout: 20_000 });
      await drawer.getByText(expectedExcerpt, { exact: true }).waitFor({ state: "visible" });
      const opened = pointerReads.at(-1);
      assert.equal(opened.evidence_pointer_id, id);
      assert.equal(opened.source_object_id, expectedSource);
      assert.equal(opened.course_id, courseId);
      assert.equal(opened.object_type, "paragraph");
      assert.ok(opened.publication_snapshot_id && opened.index_job_id && opened.domain_release_id,
        "Reader must receive the exact pinned paragraph pointer");
      assert.deepEqual({
        publication_snapshot_id: opened.publication_snapshot_id,
        index_job_id: opened.index_job_id,
        domain_release_id: opened.domain_release_id,
      }, pins);
      assert.equal(await drawer.getByRole("button", { name: "向 Tutor 提问", exact: true }).count(), 0,
        "context-only paragraph Reader must not offer a Tutor handoff");
      assert.equal(await resultCards.count(), 1);
      assert.equal(await page.locator(".learn-turn").count(), turnCount);
      assert.equal(await page.locator(".table-explain-label").count(), tableExplainCount);
      await drawer.getByRole("button", { name: "关闭上下文面板", exact: true }).click();
    }

    await page.getByRole("button", { name: "定位相邻图像", exact: true }).click();
    const figureDrawer = page.getByRole("dialog", { name: "教材来源快照" });
    await figureDrawer.waitFor({ state: "visible", timeout: 20_000 });
    await figureDrawer.getByText("图像语义尚未解析；当前只能定位，不能据此解释图像内容。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await figureDrawer.getByRole("button", { name: "向 Tutor 提问", exact: true }).count(), 0);
    await figureDrawer.getByRole("button", { name: "关闭上下文面板", exact: true }).click();

    noPinnedPointers = true;
    await page.getByLabel("搜索教材").fill(`${query} no-pin synthetic fixture`);
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    await page.getByText("合成表格结果", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await resultCards.count(), 1);
    assert.equal(await page.getByRole("button", { name: "查看图注来源", exact: true }).count(), 0,
      "a no-pin caption with no pointer ID must not render");
    assert.equal(await page.getByRole("button", { name: "查看相邻段落来源", exact: true }).count(), 0,
      "an explains paragraph with no pointer ID must not render");
    assert.equal(await page.getByRole("button", { name: /定位相邻图像/ }).count(), 0,
      "wrong object type with a stray pointer ID must not render a context action");

    const tutorWrites = writes.filter(({ path }) => path === "/api/v1/chat/sessions" || path.endsWith("/turns"));
    assert.deepEqual(tutorWrites, [], "no Tutor session creation or turn writes are permitted");
    assert.ok(writes.every(({ path }) => path === "/api/v1/knowledge/search"),
      "read-only search is the only POST-shaped request after login");
    assert.deepEqual(pageErrors, []);
    console.log("PASS UI-012 synthetic harness: exact pinned Reader pointers open in context; no-pin/no-ID and invalid closure rows hidden; Figure remains location-only; zero Tutor/session writes");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
