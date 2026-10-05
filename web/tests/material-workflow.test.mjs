import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = path => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("retired teacher materials component stays read-only", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  assert.match(teacher, /普通教师直接上传、解析、索引或发布教材/);
  assert.match(teacher, /联系课程内容管理员/);
  for (const legacyWrite of [
    "uploadMaterialResumable",
    "/material-versions/${version.id}/parse",
    "/material-versions/${version.id}/embed",
    "/material-versions/${version.id}/publish",
    "/parse-review-issues/",
  ]) assert.equal(teacher.includes(legacyWrite), false, `${legacyWrite} must stay retired`);
});

test("active teacher materials page is tested by the P2-08 read-only contract", () => {
  const retiredContract = read("./p2-08-material-authoring-exit.test.mjs");
  assert.match(retiredContract, /教师教材页保持只读/);
});
