import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("V2 workspaces consume implemented API capabilities", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  const student = read("../components/StudentWorkspace.tsx");
  const assessments = read("../components/StudentAssessments.tsx");
  const learning = read("../components/StudentLearningSession.tsx");
  assert.match(teacher, /\/material-versions\/\$\{version\.id\}\/parse/);
  assert.match(teacher, /\/material-versions\/\$\{version\.id\}\/publish/);
  assert.match(student, /\/knowledge\/search/);
  assert.match(student, /streamChatTurn/);
  assert.match(assessments, /\/attempts\/\$\{attemptId\}\/submit/);
  assert.match(learning, /\/learning-sessions/);
});

test("V2 proxy keeps the browser on the cookie origin", () => {
  const config = read("../next.config.ts");
  const client = read("../lib/api.ts");
  assert.match(config, /source: "\/api\/:path\*"/);
  assert.match(client, /credentials: "include"/);
});
