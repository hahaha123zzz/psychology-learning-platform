import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const selectionStorage = fs.readFileSync(new URL("../lib/reader-selection-context.ts", import.meta.url), "utf8");
const browser = fs.readFileSync(new URL("./student-learn-selection-tutor-browser.cjs", import.meta.url), "utf8");

test("Tutor turn prefers a selected Table pointer and otherwise uses the course-scoped Reader pointer ID", () => {
  assert.match(learn, /const selectedPointerId = selectedTablePointer\?\.evidence_pointer_id \?\? \(selectionContextPointerId \|\| undefined\)/);
  assert.match(learn, /previous\.selectedPointerId === selectedPointerId/);
  assert.match(learn, /pendingTurn\.current = \{ sessionId: activeSession, content, selectedPointerId, clientTurnId \}/);
  assert.match(learn, /clientTurnId, selectedPointerId \? \[selectedPointerId\] : undefined/);
  assert.match(learn, /clearReaderSelectionForCourse\(courseId\)/);
  assert.match(learn, /onClick=\{clearReaderSelection\}>清除选择/);
  assert.match(learn, /setQuestion\(content\)/);
  assert.match(learn, /setNotice\(`\$\{reasonText\(reason\)\} 你的问题仍保留在输入框/);
  assert.match(learn, /已将一个固定资料来源带回当前学习上下文/);
  assert.match(selectionStorage, /keys\.length !== 2/);
  assert.doesNotMatch(selectionStorage, /excerpt|selected_text|object_id|bbox|physical_page|material_version/);
});

test("API serializes at most one selected pointer ID and no Reader content or location fields", () => {
  const turnApi = api.slice(api.indexOf("export async function streamChatTurn"));
  assert.match(turnApi, /selectedEvidencePointerIds\?: string\[\]/);
  assert.match(turnApi, /selectedEvidencePointerIds\.length > 1/);
  assert.match(turnApi, /selected_evidence_pointer_ids: selectedEvidencePointerIds/);
  assert.doesNotMatch(turnApi, /excerpt|selected_text|object_id|bbox|physical_page|material_version/);
});

test("mock browser harness checks the outgoing ID-only turn, exact citation, refresh and clear", () => {
  assert.match(browser, /selected_evidence_pointer_ids/);
  assert.match(browser, /assert\.deepEqual\(turnBody\.selected_evidence_pointer_ids, \[pointerId\]\)/);
  assert.match(browser, /assert\.equal\(turnBody\.content, question\)/);
  assert.match(browser, /citationEvent\.evidence_pointer_id, pointerId/);
  assert.match(browser, /page\.reload\(\)/);
  assert.match(browser, /clearReaderSelection|清除选择/);
  assert.match(browser, /course change clears the prior course pointer/);
  assert.match(browser, /Synthetic pointer excerpt/);
});
