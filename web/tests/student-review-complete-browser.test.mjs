import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Review-only browser audit requires an existing due synthetic wrong-answer task and one verify write", () => {
  const browser = fs.readFileSync(
    new URL("./student-review-complete-browser.cjs", import.meta.url),
    "utf8",
  );
  assert.match(browser, /item\.status === "pending"/);
  assert.match(browser, /Date\.parse\(item\.due_at\) <= Date\.now\(\)/);
  assert.match(browser, /reason === "wrong_answer"/);
  assert.match(browser, /question\?\.stem/);
  assert.match(browser, /selected_keys, \["A"\]/);
  assert.match(browser, /writes\.length, 1/);
  assert.match(browser, /must use an existing due wrong-answer review task/);
});
