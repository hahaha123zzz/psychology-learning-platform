import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const storage = read("../lib/reader-selection-context.ts");
const learn = read("../components/StudentLearnPage.tsx");

test("SelectionContext sessionStorage payload is restricted to course and persistent pointer IDs", () => {
  assert.match(storage, /readerSelectionContextKey = "student-learn-selection-context"/);
  assert.match(storage, /JSON\.stringify\(\{\s*course_id: courseId,\s*evidence_pointer_id: evidencePointerId,\s*\}\s*satisfies ReaderSelectionContext\)/);
  assert.match(storage, /keys\.length !== 2/);
  assert.match(storage, /keys\[0\] !== "course_id"/);
  assert.match(storage, /keys\[1\] !== "evidence_pointer_id"/);
  assert.doesNotMatch(storage, /excerpt|selected_text|material_version|answer|content:/);
});

test("Learn restores only an exact route-course match and clears storage on clear or course switch", () => {
  assert.match(learn, /useSyncExternalStore\([\s\S]*readReaderSelectionPointerId\(courseId\)[\s\S]*\(\) => ""/);
  assert.match(storage, /value\?\.course_id === courseId \? value\.evidence_pointer_id : ""/);
  assert.match(learn, /clearReaderSelectionForCourse\(courseId\)/);
  assert.match(storage, /if \(value\?\.course_id === courseId\) return;[\s\S]*removeItem\(readerSelectionContextKey\)/);
  assert.match(learn, /button type="button" onClick=\{clearReaderSelection\}>清除选择/);
});

test("Restored SelectionContext reopens only through EvidencePointerDrawer with the persistent ID", () => {
  assert.match(learn, /EvidencePointerDrawer label="重新打开所选来源" onReturnToLearn=\{returnReaderSelection\} pointerId=\{selectionContextPointerId\}/);
  assert.match(storage, /window\.sessionStorage\.setItem/);
  assert.doesNotMatch(learn, /api<[^>]+>\([^\n]*selectionContextPointerId|fetch\([^\n]*selectionContextPointerId/);
});

test("Synthetic refresh/cross-course browser harness checks the exact storage payload and no writes", () => {
  const browser = read("./student-learn-selection-context-browser.cjs");
  assert.match(browser, /page\.evaluate\(\(key\) => sessionStorage\.getItem\(key\), storageKey\)/);
  assert.match(browser, /JSON\.stringify\(\{ course_id: courseA, evidence_pointer_id: pointerId \}\)/);
  assert.match(browser, /page\.reload\(\)/);
  assert.match(browser, /courseB/);
  assert.match(browser, /assert\.deepEqual\(businessWrites, \[\],/);
  assert.match(browser, /Synthetic pointer excerpt/);
});
