import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const reader = fs.readFileSync(new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url), "utf8");

test("Figure Reader exposes only location and unresolved semantics for an empty excerpt", () => {
  assert.match(reader, /view\.excerpt \|\| \(view\.object_type === "figure"[\s\S]*?该对象只保存了图像位置；系统未解析图像含义。/);
  assert.match(reader, /view\.object_type === "figure" && !view\.excerpt\.trim\(\)/);
  assert.match(reader, /图像语义尚未解析；当前只能定位，不能据此解释图像内容。/);
  assert.match(reader, /暂无可验证的页内坐标/);
});

test("Figure has no Tutor handoff while Tutor CTA stays limited to non-empty native tables", () => {
  assert.match(reader, /view\.object_type === "table" && view\.excerpt\.trim\(\) && onAskTutor/);
  assert.doesNotMatch(reader, /view\.object_type === "figure"[^\n]*onAskTutor|view\.object_type === "figure"[^\n]*向 Tutor 提问/);
  assert.match(learn, /neighbor\.object_type === "figure" && \(neighbor\.relation_type === "previous" \|\| neighbor\.relation_type === "next"\) && neighbor\.evidence_pointer_id/);
  assert.match(learn, /阅读顺序相邻图像 · 仅定位，图像语义暂不可解释/);
  assert.match(learn, /EvidencePointerDrawer label="定位相邻图像"/);
  assert.doesNotMatch(learn, /onAskTutor=\{[^}]*figure/);
});

test("Learn cannot label Figure as TableExplain during live turns or saved-session restore", () => {
  assert.match(learn, /explanation\?: "table"/);
  assert.match(learn, /objectContext\?\.type === "table"/);
  assert.match(learn, /eventData\.data\.object_type === "table"/);
  assert.match(learn, /turn\.explanation === "table" && <small className="table-explain-label">/);
  assert.doesNotMatch(learn, /objectContext\?\.type === "figure"|eventData\.data\.object_type === "figure"/);
});

test("Figure browser verification is read-only and never creates or sends a Tutor turn", () => {
  const browser = fs.readFileSync(new URL("./student-learn-figure-safety-browser.cjs", import.meta.url), "utf8");
  assert.match(browser, /UI008_SESSION_ID/);
  assert.match(browser, /\/api\/v1\/chat\/sessions\/\$\{encodeURIComponent\(id\)\}/);
  assert.match(browser, /session\.body\.data\.mode, "course_qa"/);
  assert.match(browser, /session\.body\.data\.status, "active"/);
  assert.match(browser, /定位相邻图像/);
  assert.match(browser, /图像语义尚未解析；当前只能定位，不能据此解释图像内容。/);
  assert.match(browser, /向 Tutor 提问/);
  assert.match(browser, /assert\.equal\(tutorTurns\.length, 0/);
  assert.match(browser, /invalidPointer\.status, 404/);
  assert.match(browser, /figurePointer\.excerpt\.trim\(\), ""/);
  assert.doesNotMatch(browser, /streamChatTurn|fetch\([^)]*\/turns|method:\s*["']POST["']/);
});
