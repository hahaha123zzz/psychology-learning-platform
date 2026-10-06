import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const drawer = read("../components/ui/ContextDrawer.tsx");
const reader = read("../components/learning/EvidencePointerDrawer.tsx");
const learn = read("../components/StudentLearnPage.tsx");
const css = read("../app/globals.css");

test("Reader drawer traps keyboard focus, closes on Escape, and restores the Learn trigger focus", () => {
  assert.match(drawer, /document\.addEventListener\("keydown", trapKeyboard\)/);
  assert.match(drawer, /event\.key === "Escape"[\s\S]*?onCloseRef\.current\(\)/);
  assert.match(drawer, /event\.shiftKey[\s\S]*?last\.focus\(\)/);
  assert.match(drawer, /!event\.shiftKey[\s\S]*?first\.focus\(\)/);
  assert.match(drawer, /returnFocusRef\.current\?\.focus\(\)/);
  assert.match(drawer, /aria-modal="true"[\s\S]*?role="dialog"/);
});

test("Reader returns only the server-confirmed persistent pointer ID to Learn SelectionContext", () => {
  assert.match(reader, /onReturnToLearn\?: \(evidencePointerId: string\) => void/);
  assert.match(reader, /if \(view\?\.evidence_pointer_id === pointerId\)[\s\S]*?onReturnToLearn\?\.\(view\.evidence_pointer_id\)/);
  assert.match(learn, /onReturnToLearn=\{returnReaderSelection\}/);
  assert.match(learn, /const \[selectionContextPointerId, setSelectionContextPointerId\] = useState\(""\)/);
  assert.match(learn, /setSelectionContextPointerId\(pointerId\)/);
  assert.match(learn, /className="learn-selection-context" role="status"/);
  assert.match(learn, /onClick=\{\(\) => setSelectionContextPointerId\(""\)\}/);
  assert.match(learn, /label="重新打开所选来源"[\s\S]*?pointerId=\{selectionContextPointerId\}/);
  assert.doesNotMatch(learn, /selectionContextPointerId[^\n]*(?:excerpt|material_version_id|selected_text)/);
  assert.doesNotMatch(reader, /onReturnToLearn\([^)]*,/);
});

test("Reader controls reflow at phone width and provide touch-sized actions", () => {
  assert.match(css, /\.reader-view-controls \{ display:flex; flex-wrap:wrap/);
  assert.match(css, /\.reader-view-controls \.ds-button \{ min-width:40px/);
  assert.match(css, /@media \(max-width:560px\)[\s\S]*?\.reader-page-controls \{ grid-template-columns:1fr; \}/);
  assert.match(css, /\.ds-drawer-body \{ padding:16px; \}/);
});

test("Mock browser harness uses synthetic Reader data and forbids Tutor or business writes", () => {
  const browser = read("./student-learn-reader-accessibility-browser.cjs");
  assert.match(browser, /UI013_APP_ORIGIN/);
  assert.match(browser, /Synthetic pointer excerpt/);
  assert.match(browser, /request\.method\(\) !== "GET"/);
  assert.match(browser, /assert\.deepEqual\(businessWrites, \[\],/);
  assert.match(browser, /page\.keyboard\.press\("Escape"\)/);
  assert.match(browser, /viewport: \{ width: 360/);
});
