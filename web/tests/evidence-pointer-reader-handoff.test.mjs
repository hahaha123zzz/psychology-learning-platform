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
    /onClick=\{\(\) => \{\s*onAskTutor\(view\.evidence_pointer_id\);\s*setOpen\(false\);\s*\}\}/,
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
  assert.match(
    source,
    /view\.object_type === "figure" && !view\.excerpt\.trim\(\)[\s\S]*?图像语义尚未解析；当前只能定位，不能据此解释图像内容。/,
  );
  assert.match(source, /该对象只保存了图像位置；系统未解析图像含义。/);
});
