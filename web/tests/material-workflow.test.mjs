import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = path => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("teacher material workflow uses real server state and five gated stages", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  assert.match(teacher, /\/material-versions\/\$\{versionId\}\/workflow/);
  assert.match(teacher, /\/courses\/\$\{id\}\/material-jobs/);
  assert.match(teacher, /upload: "上传", parse: "解析", review: "教师审核", index: "构建索引", publish: "发布"/);
  assert.match(teacher, /allowed_actions\[0\]/);
  assert.match(teacher, /ready_to_publish/);
});

test("upload exposes real browser progress and warns before leaving", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  const client = read("../lib/api.ts");
  assert.match(teacher, /beforeunload/);
  assert.match(teacher, /uploadProgress/);
  assert.match(client, /XMLHttpRequest/);
  assert.match(client, /request\.upload\.onprogress/);
});
