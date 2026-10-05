import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/StudentAssessments.tsx", import.meta.url),
  "utf8",
);

test("assessment deadline auto-submits once instead of locking the submit action", () => {
  assert.match(source, /autoSubmitAttempt/);
  assert.match(source, /remainingSeconds\s*!==\s*0[\s\S]*?submit\(true\)/);
  assert.doesNotMatch(source, /disabled=\{remainingSeconds\s*===\s*0\s*\|\|\s*savePending\}/);
  assert.match(source, /await api\(`\/attempts\/\$\{attemptId\}\/submit`/);
  assert.match(source, /setResult\(await api<Result>\(`\/attempts\/\$\{attemptId\}\/result`\)\)/);
});

test("a closed assessment resumes only by sealing and reading the existing attempt", () => {
  assert.match(source, /const finalizeClosedAttempt = useCallback\(async \(id: string\) => \{/);
  assert.match(source, /current_attempt_id && item\.availability === "closed"/);
  assert.match(source, /await finalizeClosedAttempt\(closedAttempt\.current_attempt_id\)/);
  assert.match(source, /item\.availability === "closed" && item\.current_attempt_id \?/);
  assert.match(source, /finalizeClosedAttempt\(item\.current_attempt_id!\).*恢复已保存结果/);
  const closedResume = source.slice(
    source.indexOf("const finalizeClosedAttempt"),
    source.indexOf("const load"),
  );
  assert.match(closedResume, /await api\(`\/attempts\/\$\{id\}\/submit`, \{ method: "POST" \}\)/);
  assert.match(closedResume, /const recoveredResult = await api<Result>\(`\/attempts\/\$\{id\}\/result`\);\s*setResult\(recoveredResult\)/);
  assert.doesNotMatch(closedResume, /\/assessments\/\$\{.*\}\/attempts|api<Detail>/);
});
