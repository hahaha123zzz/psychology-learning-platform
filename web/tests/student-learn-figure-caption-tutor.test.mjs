import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const drawer = fs.readFileSync(new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const browser = fs.readFileSync(new URL("./student-learn-figure-caption-tutor-browser.cjs", import.meta.url), "utf8");

test("Figure stays location-only while pinned caption/explains paragraphs expose Reader pointers", () => {
  const closureGuard = learn.slice(learn.indexOf("function isPinnedParagraphContext"), learn.indexOf("function StudentLearnContent"));
  assert.match(closureGuard, /neighbor\.object_type === "paragraph"/);
  assert.match(closureGuard, /neighbor\.relation_type === "caption_of" \|\| neighbor\.relation_type === "explains"/);
  assert.match(closureGuard, /neighbor\.evidence_pointer_id\.trim\(\)\.length > 0/);
  assert.match(learn, /EvidencePointerDrawer label=\{neighbor\.relation_type === "caption_of" \? "查看图注来源" : "查看相邻段落来源"\} onReturnToLearn=\{returnReaderSelection\} pointerId=\{neighbor\.evidence_pointer_id\}/);
  assert.match(learn, /阅读顺序相邻图像 · 仅定位，图像语义暂不可解释/);
  assert.match(drawer, /图像语义尚未解析；当前只能定位，不能据此解释图像内容。/);
  assert.match(drawer, /function isTutorSelectablePointer\(view: EvidencePointerView\): boolean[\s\S]*?\(view\.object_type === "paragraph" \|\| view\.object_type === "table"\) && view\.excerpt\.trim\(\)\.length > 0/);
  assert.match(drawer, /view\?\.evidence_pointer_id === pointerId && isTutorSelectablePointer\(view\)/);
  const tutorHandoff = drawer.slice(drawer.indexOf("{view.object_type === \"table\" && view.excerpt.trim() && onAskTutor"), drawer.indexOf("</Button>", drawer.indexOf("{view.object_type === \"table\" && view.excerpt.trim() && onAskTutor")));
  assert.match(tutorHandoff, /view\.object_type === "table" && view\.excerpt\.trim\(\) && onAskTutor/);
  assert.doesNotMatch(tutorHandoff, /figure|image|excerpt:/);
});

test("Tutor handoff sends the selected persistent ID only and renders the server citation pointer", () => {
  assert.match(learn, /selectedTablePointer\?\.evidence_pointer_id \?\? \(selectionContextPointerId \|\| undefined\)/);
  assert.match(learn, /clientTurnId, selectedPointerId \? \[selectedPointerId\] : undefined/);
  assert.match(learn, /previous\.selectedPointerId === selectedPointerId/);
  assert.match(learn, /eventData\.data\.evidence_pointer_id/);
  assert.match(learn, /EvidencePointerDrawer label="打开引用" onReturnToLearn=\{returnReaderSelection\} pointerId=\{citation\.pointerId\}/);
  const stream = api.slice(api.indexOf("export async function streamChatTurn"));
  assert.match(stream, /selected_evidence_pointer_ids: selectedEvidencePointerIds/);
  assert.doesNotMatch(stream, /excerpt|selected_text|object_id|bbox|physical_page|material_version/);
});

test("Synthetic browser harness rejects Figure ID and verifies the same caption ID through Citation Reader", () => {
  assert.match(browser, /Figure remains location-only/);
  assert.match(browser, /Figure close must not persist an unusable Tutor pointer/);
  assert.match(browser, /向 Tutor 提问/);
  assert.match(browser, /assert\.deepEqual\(turnBody\.selected_evidence_pointer_ids, \[captionPointerId\]\)/);
  assert.match(browser, /assert\.notEqual\(turnBody\.selected_evidence_pointer_ids\[0\], figurePointerId/);
  assert.match(browser, /source_object_id, "synthetic-caption-object"/);
  assert.match(browser, /assert\.equal\(pointerReadPaths\.at\(-1\), captionPointerId/);
  assert.match(browser, /assert\.deepEqual\(pointerReadPaths\.filter\(\(id\) => id === figurePointerId\), \[figurePointerId\]\)/);
  assert.match(browser, /selected_evidence_pointer_ids"\]\)/);
  assert.doesNotMatch(browser, /TEXTBOOK|\.pdf|openai\.com|anthropic\.com/);
});
