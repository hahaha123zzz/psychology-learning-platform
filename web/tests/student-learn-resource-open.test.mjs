import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const reader = fs.readFileSync(new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url), "utf8");
const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const labels = fs.readFileSync(new URL("../lib/material-type-label.ts", import.meta.url), "utf8");
const browser = fs.readFileSync(new URL("./student-learn-resource-open-browser.cjs", import.meta.url), "utf8");

test("material labels map server type only and unknown legacy values stay neutral", () => {
  for (const [type, label] of [["textbook", "教材"], ["slides", "课件"], ["handout", "讲义"], ["exercise", "练习资料"], ["reference", "参考资料"], ["other", "课程资料"]]) {
    assert.match(labels, new RegExp(`${type}: \\"${label}\\"`));
  }
  assert.match(labels, /MATERIAL_TYPE_LABELS\[value\] \?\? "课程资料"/);
  assert.match(labels, /: "课程资料"/);
  assert.match(learn, /materialTypeLabel\(item\.material_type\)/);
  assert.match(learn, /materialTypeLabel\(citation\.materialType\)/);
  assert.doesNotMatch(learn, /materialTypeLabel\([^)]*title/);
  assert.match(reader, /materialTypeLabel\(view\.material_type\)/);
});

test("Reader records only a displayed, matching authorized pointer and exact minimal payload once per opening", () => {
  assert.match(reader, /view\.evidence_pointer_id !== pointerId/);
  assert.match(reader, /!view\.course_id/);
  assert.match(reader, /const opening = openEventRef\.current;[\s\S]*?if \(!opening \|\| opening\.sent\) return;[\s\S]*?opening\.sent = true;/);
  assert.match(reader, /api\("\/learning-events", \{\s*method: "POST",\s*body: JSON\.stringify\(\{\s*event_key: opening\.eventKey,\s*course_id: view\.course_id,\s*evidence_pointer_id: view\.evidence_pointer_id,/);
  assert.doesNotMatch(reader, /event_key:[\s\S]{0,300}(excerpt|material_version|physical_page|dwell)/);
  assert.match(reader, /\.catch\(\(\) => \{[\s\S]*?RESOURCE_OPENED event could not be recorded/);
  assert.match(reader, /openEventRef\.current = \{ eventKey: crypto\.randomUUID\(\), sent: false \}/);
  assert.match(reader, /setView\(null\);[\s\S]*?setOpen\(true\)/);
});

test("mock browser covers single write, payload whitelist, stale-content 404, and nonblocking write failure", () => {
  assert.match(browser, /resourceWrites\.length, 1, "successful Reader open records once/);
  assert.match(browser, /\["course_id", "event_key", "evidence_pointer_id"\]/);
  assert.match(browser, /readerReturns404 = true/);
  assert.match(browser, /404 clears stale excerpt/);
  assert.match(browser, /event write failure does not block reading/);
  assert.match(browser, /initial 404 has no event write/);
  assert.match(browser, /otherWrites, \[\]/);
  assert.match(browser, /unrecognized/);
});
