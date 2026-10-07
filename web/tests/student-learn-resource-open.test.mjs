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

test("generic Learn and Reader copy stays neutral for every resource type", () => {
  for (const phrase of ["搜索教材", "课程教材", "教材来源快照", "查看教材引用", "回答以当前课程教材为依据", "教材依据", "教材内容", "围绕教材提问", "从已发布教材中检索"]) {
    assert.doesNotMatch(learn, new RegExp(phrase));
    assert.doesNotMatch(reader, new RegExp(phrase));
  }
  assert.match(learn, /搜索课程资料/);
  assert.match(learn, /从当前课程资料中检索内容，并查看可核验的来源/);
  assert.match(learn, /回答以当前课程资料为依据/);
  assert.match(learn, /围绕课程资料提问/);
  assert.match(learn, /资料引用 \$\{index \+ 1\}/);
  assert.match(learn, /课程资料来源/);
  assert.match(learn, /item\.object_type === "figure" \? "图像对象/);
  assert.match(learn, /materialTypeLabel\(item\.material_type\)/);
  assert.match(learn, /materialTypeLabel\(citation\.materialType\)/);
  assert.match(reader, /label = "查看来源资料"/);
  assert.match(reader, /title="资料来源"/);
  assert.match(reader, /暂时无法读取资料来源/);
  assert.match(reader, /materialTypeLabel\(view\.material_type\)/);
  assert.match(browser, /getByRole\("dialog", \{ name: "资料来源" \}\)/);
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
