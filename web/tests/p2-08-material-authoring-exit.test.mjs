import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/TeacherMaterialsPage.tsx", import.meta.url),
  "utf8",
);

test("教师教材页保持只读，不暴露旧上传、解析、索引和发布操作", () => {
  assert.match(source, /教师端不开放教材上传、解析、索引或发布操作/);
  assert.match(source, /联系课程内容管理员/);
  for (const legacyWrite of [
    "uploadMaterialResumable",
    "/upload-sessions",
    "/material-versions/${version.id}/parse",
    "/material-versions/${version.id}/embed",
    "/material-versions/${version.id}/publish",
  ]) {
    assert.equal(source.includes(legacyWrite), false, `不应暴露旧写入操作：${legacyWrite}`);
  }
});
