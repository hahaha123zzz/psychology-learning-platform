import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url),
  "utf8",
);

test("Reader handoff callback accepts only the server-loaded persistent pointer ID", () => {
  assert.match(source, /onAskTutor\?: \(evidencePointerId: string\) => void/);
  assert.match(
    source,
    /onClick=\{\(\) => \{\s*onAskTutor\(view\.evidence_pointer_id\);\s*closeReader\(\);\s*\}\}/,
  );
  assert.doesNotMatch(source, /onAskTutor\([^)]*,/);
});

test("Tutor CTA is limited to a non-empty table excerpt and remains keyboard-operable", () => {
  assert.match(
    source,
    /view\.object_type === "table" && view\.excerpt\.trim\(\) && onAskTutor/,
  );
  assert.match(source, /<Button[\s\S]*?type="button"[\s\S]*?>\s*向 Tutor 提问\s*<\/Button>/);
  assert.doesNotMatch(source, /view\.object_type === "figure"[^\n]*向 Tutor 提问/);
});

test("An empty figure excerpt is explicitly location-only with unresolved semantics", () => {
  const figureBranch = source.match(
    /\{view\.object_type === "figure" && !view\.excerpt\.trim\(\) && \([\s\S]*?\)\}/,
  )?.[0];
  assert.ok(figureBranch, "空 excerpt Figure 分支存在");
  assert.match(figureBranch, /图像语义尚未解析；当前只能定位，不能据此解释图像内容。/);
  assert.doesNotMatch(figureBranch, /onAskTutor|向 Tutor 提问/);
  assert.match(source, /该对象只保存了图像位置；系统未解析图像含义。/);
});

test("Figure Reader exposes only server pointer location metadata and no semantic image claim", () => {
  assert.match(source, /api<EvidencePointerView>\(`\/evidence-pointers\/\$\{pointerId\}`\)/);
  assert.match(source, /\{view\.material_title\}/);
  assert.match(source, /view\.chapter_path \|\| "未记录章节"/);
  assert.match(source, /view\.physical_page \? ` · 物理页 \$\{view\.physical_page\}`/);
  assert.match(source, /\$\{view\.object_type\}/);
  assert.match(source, /view\.material_version_id/);
  assert.match(source, /view\.bbox/);
  assert.match(source, /资料物理页 \$\{visiblePage\.physicalPage\}，红框标出引用位置/);
  assert.doesNotMatch(source, /图像内容是|图中显示|该图表说明/);
});
