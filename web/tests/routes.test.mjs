import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

test("workspace route contract is present", () => {
  const source = fs.readFileSync(new URL("../lib/routes.ts", import.meta.url), "utf8");
  assert.match(source, /student:\s*"\/student"/);
  assert.match(source, /teacher:\s*"\/teacher"/);
  assert.match(source, /admin:\s*"\/admin"/);
});

