/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const origin = process.env.UI035_APP_ORIGIN ?? "http://127.0.0.1:3001";
const email = process.env.UI035_STUDENT_EMAIL;
const password = process.env.UI035_STUDENT_PASSWORD;
const executablePath = process.env.UI035_CHROME_PATH;
const courseId = "01M00000000000000000000401";
const sessionId = "01M00000000000000000000402";
const figurePointerId = "01M00000000000000000000403";
const captionPointerId = "01M00000000000000000000404";
const explainsPointerId = "01M00000000000000000000405";
const storageKey = "student-learn-selection-context";
const pins = {
  publication_snapshot_id: "01M00000000000000000000411",
  index_job_id: "01M00000000000000000000412",
  domain_release_id: "01M00000000000000000000413",
};
const envelope = (data) => ({ data, meta: { request_id: "ui035-synthetic", server_time: "2026-10-07T00:00:00Z" } });
const pointerReadPaths = [];
const pointerReadBodies = [];
const tutorBodies = [];

function pointer(pointerId) {
  const isFigure = pointerId === figurePointerId;
  const isCaption = pointerId === captionPointerId;
  return {
    evidence_pointer_id: pointerId,
    course_id: courseId,
    material_title: "Synthetic course resource",
    material_id: "synthetic-material",
    material_version_id: "synthetic-version",
    ...pins,
    source_object_id: isFigure ? "synthetic-figure-object" : isCaption ? "synthetic-caption-object" : "synthetic-explains-object",
    chapter_path: "Synthetic chapter / figure-caption relation",
    physical_page: 7,
    object_type: isFigure ? "figure" : "paragraph",
    coordinate_space: "unavailable",
    bbox: isFigure ? [10, 20, 100, 120] : null,
    anchors: [],
    excerpt: isFigure ? "" : isCaption ? "Synthetic approved caption paragraph." : "Synthetic approved explains paragraph.",
    excerpt_sha256: isFigure ? "" : "synthetic-only",
  };
}

async function main() {
  if (!email || !password) throw new Error("Set UI035_STUDENT_EMAIL and UI035_STUDENT_PASSWORD to synthetic local credentials.");
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage({ viewport: { width: 393, height: 844 } });
  let savedTutorTurn;

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/v1/auth/login" && method === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({})) });
    } else if (path === "/api/v1/me" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ display_name: "Synthetic learner", platform_roles: [] })) });
    } else if (path === `/api/v1/courses/${courseId}/materials` && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([{ id: "synthetic-material", title: "Synthetic course resource", current_version: { id: "synthetic-version", version_no: 1, status: "published" } }])) });
    } else if (path === "/api/v1/student/intervention-runs" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope([])) });
    } else if (path === `/api/v1/chat/sessions/${sessionId}` && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({
        id: sessionId,
        course_id: courseId,
        mode: "course_qa",
        status: "active",
        turns: savedTutorTurn ? [savedTutorTurn] : [],
      })) });
    } else if (path === "/api/v1/knowledge/search" && method === "POST") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope({ items: [{
        evidence_id: "synthetic-figure-hit",
        evidence_pointer_id: figurePointerId,
        title: "Synthetic figure location",
        text: "",
        object_type: "figure",
        material_type: "other",
        physical_page: 7,
        closure: [
          { object_id: "synthetic-caption-object", object_type: "paragraph", relation_type: "caption_of", evidence_pointer_id: captionPointerId, physical_page: 7 },
          { object_id: "synthetic-explains-object", object_type: "paragraph", relation_type: "explains", evidence_pointer_id: explainsPointerId, physical_page: 7 },
        ],
      }] })) });
    } else if ([figurePointerId, captionPointerId, explainsPointerId].some((id) => path === `/api/v1/evidence-pointers/${id}`) && method === "GET") {
      const pointerId = path.split("/").at(-1);
      pointerReadPaths.push(pointerId);
      const body = pointer(pointerId);
      pointerReadBodies.push(body);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope(body)) });
    } else if (path === "/api/v1/learning-events" && method === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(envelope({ id: "synthetic-resource-opened" })) });
    } else if (path === `/api/v1/chat/sessions/${sessionId}/turns` && method === "POST") {
      const body = request.postDataJSON();
      tutorBodies.push(body);
      const citation = { evidence_pointer_id: captionPointerId, label: "Synthetic caption paragraph citation", material_type: "other" };
      const answer = "Synthetic explanation grounded in the caption paragraph.";
      savedTutorTurn = { role: "tutor", content: answer, citations: [citation] };
      const frames = [
        `event: delta\ndata: ${JSON.stringify({ text: answer })}`,
        `event: citation\ndata: ${JSON.stringify(citation)}`,
        `event: done\ndata: ${JSON.stringify({ saved: true })}`,
      ].join("\n\n") + "\n\n";
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: frames });
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { code: "UNEXPECTED_SYNTHETIC_ROUTE", message: `Unexpected route ${method} ${path}` }, request_id: "ui035-unexpected" }) });
    }
  });

  try {
    await page.goto(`${origin}/login`);
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel("密码").fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForURL((url) => url.pathname === "/student", { timeout: 15_000 });
    await page.goto(`${origin}/student/courses/${courseId}/learn?session_id=${sessionId}`);
    await page.getByLabel("搜索课程资料").fill("synthetic figure caption");
    await page.getByRole("button", { name: "搜索", exact: true }).click();
    const figureResult = page.locator(".evidence-list > article").first();
    await figureResult.waitFor({ state: "visible" });
    assert.equal(await page.getByRole("button", { name: "查看图注来源", exact: true }).count(), 1);
    assert.equal(await page.getByRole("button", { name: "查看相邻段落来源", exact: true }).count(), 1);

    await page.getByRole("button", { name: "查看固定来源快照", exact: true }).click();
    const reader = page.getByRole("dialog", { name: "资料来源" });
    await reader.getByText("图像语义尚未解析；当前只能定位，不能据此解释图像内容。", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await reader.getByRole("button", { name: "向 Tutor 提问", exact: true }).count(), 0, "empty Figure pointer stays location-only");
    assert.equal(tutorBodies.length, 0, "opening Figure Reader never sends a Tutor turn");
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), null, "Figure close must not persist an unusable Tutor pointer");

    await page.getByRole("button", { name: "查看图注来源", exact: true }).click();
    await reader.getByText("Synthetic approved caption paragraph.", { exact: true }).waitFor({ state: "visible" });
    assert.equal(await reader.getByRole("button", { name: "向 Tutor 提问", exact: true }).count(), 0, "paragraph closure is selected by returning to Learn, not by an excerpt-bearing CTA");
    const captionGet = pointerReadPaths.at(-1);
    assert.equal(captionGet, captionPointerId);
    const selectedCaption = pointerReadBodies.at(-1);
    assert.equal(selectedCaption.course_id, courseId);
    assert.equal(selectedCaption.object_type, "paragraph");
    assert.equal(selectedCaption.source_object_id, "synthetic-caption-object");
    assert.deepEqual({
      publication_snapshot_id: selectedCaption.publication_snapshot_id,
      index_job_id: selectedCaption.index_job_id,
      domain_release_id: selectedCaption.domain_release_id,
    }, pins, "Reader returns the exact pinned caption paragraph pointer");
    await page.keyboard.press("Escape");
    await reader.waitFor({ state: "hidden" });
    assert.equal(await page.evaluate((key) => sessionStorage.getItem(key), storageKey), JSON.stringify({ course_id: courseId, evidence_pointer_id: captionPointerId }));

    const question = "请解释这个合成图注所描述的内容。";
    const input = page.getByRole("textbox", { name: "围绕课程资料提问" });
    await input.fill(question);
    await input.press("Enter");
    await page.getByText("Synthetic caption paragraph citation", { exact: true }).waitFor({ state: "visible" });
    assert.equal(tutorBodies.length, 1);
    const turnBody = tutorBodies[0];
    assert.deepEqual(Object.keys(turnBody).sort(), ["client_turn_id", "content", "selected_evidence_pointer_ids"]);
    assert.equal(turnBody.content, question);
    assert.deepEqual(turnBody.selected_evidence_pointer_ids, [captionPointerId]);
    assert.notEqual(turnBody.selected_evidence_pointer_ids[0], figurePointerId, "empty Figure pointer is never sent to Tutor");
    assert.equal(await page.locator(".learn-turn.tutor .table-explain-label").count(), 0, "caption answer is not mislabeled as TableExplain");
    const tutorTurn = page.locator(".learn-turn.tutor").last();
    assert.doesNotMatch(await tutorTurn.innerText(), /图像语义|识别图像|图像解释/);
    const citationButton = tutorTurn.getByRole("button", { name: "打开引用", exact: true });
    await citationButton.click();
    await reader.getByText("Synthetic approved caption paragraph.", { exact: true }).waitFor({ state: "visible" });
    assert.equal(pointerReadPaths.at(-1), captionPointerId, "citation Reader performs a fresh GET for the same caption paragraph pointer");
    assert.equal(pointerReadBodies.at(-1).source_object_id, "synthetic-caption-object");
    assert.deepEqual({
      publication_snapshot_id: pointerReadBodies.at(-1).publication_snapshot_id,
      index_job_id: pointerReadBodies.at(-1).index_job_id,
      domain_release_id: pointerReadBodies.at(-1).domain_release_id,
    }, pins, "citation Reader remains on the identical pinned paragraph");
    assert.deepEqual(pointerReadPaths.filter((id) => id === figurePointerId), [figurePointerId]);
    assert.deepEqual(pointerReadPaths.filter((id) => id === captionPointerId), [captionPointerId, captionPointerId]);
    assert.equal(pointerReadPaths.includes(explainsPointerId), false, "unselected explains context is not sent or read as selected evidence");
    console.log("PASS UI-035 synthetic mock browser: Figure remains location-only; pinned caption pointer flows through Reader→Tutor→same Citation→Reader with ID-only payload");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
