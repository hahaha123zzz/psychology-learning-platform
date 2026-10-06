import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");

test("Learn shows only pinned paragraph caption/explains pointers inside their existing search hit", () => {
  const predicate = learn.slice(learn.indexOf("function isPinnedParagraphContext"), learn.indexOf("function StudentLearnContent"));
  assert.match(predicate, /neighbor\.object_type === "paragraph"/);
  assert.match(predicate, /neighbor\.relation_type === "caption_of" \|\| neighbor\.relation_type === "explains"/);
  assert.match(predicate, /typeof neighbor\.evidence_pointer_id === "string"/);
  assert.match(predicate, /neighbor\.evidence_pointer_id\.trim\(\)\.length > 0/);

  const context = learn.slice(learn.indexOf("item.closure?.filter(isPinnedParagraphContext)"), learn.indexOf("item.closure?.filter((neighbor) => neighbor.object_type === \"figure\""));
  assert.match(context, /图注上下文（非独立检索命中）/);
  assert.match(context, /解释段落上下文（非独立检索命中）/);
  assert.match(context, /EvidencePointerDrawer label=\{neighbor\.relation_type === "caption_of" \? "查看图注来源" : "查看相邻段落来源"\} pointerId=\{neighbor\.evidence_pointer_id\}/);
  assert.doesNotMatch(context, /onAskTutor|onClick|<article/);
  assert.match(learn, /results\.map\(\(item, index\) => <article[\s\S]*?item\.closure\?\.filter\(isPinnedParagraphContext\)\.map/);
});

test("missing pointer IDs stay hidden while Figure retains its location-only entry", () => {
  const predicate = learn.slice(learn.indexOf("function isPinnedParagraphContext"), learn.indexOf("function StudentLearnContent"));
  assert.match(predicate, /typeof neighbor\.evidence_pointer_id === "string"/);
  assert.match(predicate, /neighbor\.evidence_pointer_id\.trim\(\)\.length > 0/);
  assert.match(learn, /neighbor\.object_type === "figure" && \(neighbor\.relation_type === "previous" \|\| neighbor\.relation_type === "next"\) && neighbor\.evidence_pointer_id/);
  assert.match(learn, /阅读顺序相邻图像 · 仅定位，图像语义暂不可解释/);
  assert.match(learn, /EvidencePointerDrawer label="定位相邻图像"/);
});

test("browser harness checks exact Reader pointer pins, no-ID fixtures, and zero Tutor writes", () => {
  const browser = fs.readFileSync(new URL("./student-learn-closure-context-browser.cjs", import.meta.url), "utf8");
  assert.match(browser, /UI012_SESSION_ID/);
  assert.match(browser, /UI012_COURSE_ID/);
  assert.match(browser, /UI012_QUERY/);
  assert.match(browser, /no-pin synthetic fixture|无 ID 的合成 closure/);
  assert.match(browser, /查看图注来源/);
  assert.match(browser, /查看相邻段落来源/);
  assert.match(browser, /publication_snapshot_id/);
  assert.match(browser, /index_job_id/);
  assert.match(browser, /domain_release_id/);
  assert.match(browser, /assert\.deepEqual\(tutorWrites, \[\]/);
  assert.doesNotMatch(browser, /streamChatTurn|method:\s*["']POST["']/);
});
