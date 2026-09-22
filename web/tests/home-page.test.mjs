import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("home page presents the teacher and student workspaces", () => {
  const source = fs.readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(source, /href="\/login\?next=\/teacher"/);
  assert.match(source, /href="\/login\?next=\/student"/);
  assert.doesNotMatch(source, /FOUNDATION · V0\.1/);
});
