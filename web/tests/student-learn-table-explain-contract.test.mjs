import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/StudentLearnPage.tsx", import.meta.url),
  "utf8",
);
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("Reader handoff reloads and validates only a server-owned native table pointer", () => {
  const selection = source.slice(source.indexOf("async function selectTablePointer"), source.indexOf("async function search"));
  assert.match(selection, /api<TablePointerResponse>\(`\/evidence-pointers\/\$\{encodeURIComponent\(pointerId\)\}`\)/);
  assert.match(selection, /pointer\.evidence_pointer_id !== pointerId/);
  assert.match(selection, /pointer\.course_id !== courseId/);
  assert.match(selection, /pointer\.object_type !== "table"/);
  assert.match(selection, /!pointer\.excerpt\.trim\(\)/);
  assert.doesNotMatch(selection, /excerpt:\s*pointer\.excerpt/);
  assert.match(source, /onAskTutor=\{item\.object_type === "table" \? selectTablePointer : undefined\}/);
  assert.match(source, /selectedTablePointer\.material_title/);
  assert.match(source, /selectedTablePointer\.chapter_path/);
  assert.match(source, /selectedTablePointer\.physical_page/);
});

test("the browser script requires and restores an existing synthetic course_qa session", () => {
  const browser = fs.readFileSync(new URL("./student-learn-table-explain-browser.cjs", import.meta.url), "utf8");
  assert.match(browser, /const sessionId = process\.env\.UI007_SESSION_ID/);
  assert.match(browser, /if \(!email \|\| !password \|\| !sessionId\)/);
  assert.match(browser, /\/chat\/sessions\/\$\{encodeURIComponent\(id\)\}/);
  assert.match(browser, /session\.body\.data\.course_id, course\.id/);
  assert.match(browser, /session\.body\.data\.mode, "course_qa"/);
  assert.match(browser, /learn\?session_id=\$\{encodeURIComponent\(sessionId\)\}/);
  assert.match(browser, /persistedWrites\.filter\(\(item\) => item\.path === "\/api\/v1\/chat\/sessions"\)\.length, 0/);
  assert.match(browser, /persistedWrites\.filter\(\(item\) => item\.path\.endsWith\("\/turns"\)\)\.length, 1/);
  assert.match(browser, /writes\.filter\(\(item\) => item\.path === "\/api\/v1\/knowledge\/search"\)\.length, 1/);
  assert.match(browser, /publication_snapshot_id/);
  assert.match(browser, /index_job_id/);
  assert.match(browser, /domain_release_id/);
  assert.match(browser, /const restoredTutorTurnCount = session\.body\.data\.turns\.filter\(\(turn\) => turn\.role === "tutor"\)\.length/);
  assert.match(browser, /page\.waitForFunction\(\(count\) => document\.querySelectorAll\("\.learn-turn\.tutor"\)\.length === count \+ 1/);
  assert.match(browser, /const latestTutorTurn = page\.locator\("\.learn-turn\.tutor"\)\.last\(\)/);
  assert.match(browser, /const tableExplainLabel = latestTutorTurn\.locator\("\.table-explain-label"\)\.first\(\)/);
  assert.match(browser, /await tableExplainLabel\.waitFor\(\{ state: "visible", timeout: 60_000 \}\)/);
  assert.match(browser, /assert\.equal\(await tableExplainLabel\.count\(\), 1/);
  assert.match(browser, /assert\.equal\(\(await tableExplainLabel\.innerText\(\)\)\.trim\(\), "表格解释 · 来自已核验的表格引用"/);
  assert.doesNotMatch(browser, /page\.getByText\("表格解释 · 来自已核验的表格引用"/);
  assert.doesNotMatch(browser, /latestTutorTurn\.getByText\(/);
});

test("Tutor request transmits at most one pointer ID and binds retries to pointer selection", () => {
  assert.match(api, /selectedEvidencePointerIds\?: string\[\]/);
  assert.match(api, /selectedEvidencePointerIds\.length > 1/);
  assert.match(api, /selected_evidence_pointer_ids: selectedEvidencePointerIds/);
  assert.doesNotMatch(api.slice(api.indexOf("export async function streamChatTurn")), /excerpt|object_id|bbox|image/);
  assert.match(source, /previous\.selectedPointerId === selectedPointerId/);
  assert.match(source, /clientTurnId, selectedPointerId \? \[selectedPointerId\] : undefined/);
});

test("Only matching server TableExplain state labels the turn and citations keep Reader pointer IDs", () => {
  const send = source.slice(source.indexOf("async function send"), source.indexOf("const visibleNotice"));
  assert.match(send, /stage === "explaining_object"/);
  assert.match(send, /eventData\.data\.object_type === "table"/);
  assert.match(send, /eventData\.data\.evidence_pointer_id === selectedPointerId/);
  assert.match(source, /pendingExplanation: "table" as const/);
  assert.match(send, /eventData\.data\.saved === true && item\.pendingExplanation === "table" && hasExactTableCitation/);
  assert.match(source, /turn\.explanation === "table" && <small className="table-explain-label">表格解释/);
  assert.match(send, /eventData\.data\.evidence_pointer_id/);
  assert.match(source, /EvidencePointerDrawer label="打开引用" onReturnToLearn=\{returnReaderSelection\} pointerId=\{citation\.pointerId\}/);
  assert.match(source, /stage === "explaining_object" &&/);
});

test("Saved Tutor sessions restore TableExplain only from server verification matching its citation", () => {
  assert.match(source, /verification\?: unknown/);
  assert.match(source, /verification\?\.object_context/);
  assert.match(source, /objectContext\?\.type === "table"/);
  assert.match(source, /citations\.some\(\(citation\) => citation\.pointerId === objectContext\.evidence_pointer_id\)/);
  assert.match(source, /explanation: isVerifiedTableTurn \? "table" : undefined/);
});
