import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const script = fs.readFileSync(new URL("./student-home-task-resume-browser.cjs", import.meta.url), "utf8");

test("UI-010 Home CTA audit restores the same existing task without business writes", () => {
  assert.match(script, /UI010_STUDENT_EMAIL/);
  assert.match(script, /UI010_STUDENT_PASSWORD/);
  assert.match(script, /fetch\("\/api\/v1\/student\/home"/);
  assert.match(script, /task\.task_id/);
  assert.match(script, /task\.course_id/);
  assert.match(script, /task\.state_version/);
  assert.match(script, /getByRole\("link", \{ name: "继续当前任务", exact: true \}\)/);
  assert.match(script, /sessionStorage\.getItem\("student-learning-task"\)/);
  assert.match(script, /student\/learning\/tasks\/\$\{encodeURIComponent\(task\.task_id\)\}/);
  assert.match(script, /restored\?\.course_id, task\.course_id/);
  assert.match(script, /restored\?\.state, task\.state/);
  assert.match(script, /restored\?\.state_version, task\.state_version/);
  assert.match(script, /assert\.deepEqual\(businessWrites, \[\]/);
  assert.match(script, /assert\.deepEqual\(apiErrors, \[\]/);
  assert.match(script, /assert\.deepEqual\(pageErrors, \[\]/);
  assert.match(script, /request\.method\(\), path: url\.pathname/);
  assert.match(script, /interruptedHomeReads = new Set\(\["\/api\/v1\/student\/home", "\/api\/v1\/courses"\]\)/);
  assert.match(script, /item\.method === "GET" && interruptedHomeReads\.has\(item\.path\) && item\.error === "net::ERR_ABORTED"/);
  assert.match(script, /await page\.waitForFunction\(\(expectedTitle\) =>[\s\S]*item\.textContent\?\.trim\(\) === expectedTitle/);
  assert.doesNotMatch(script, /method:\s*["']POST["']|\/learning-sessions|student\/learning\/tasks\/.*\/(respond|pause|resume)/);
});
