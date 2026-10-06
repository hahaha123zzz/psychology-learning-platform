import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { studentMaterialVersion } from "../lib/student-material-version.ts";

const learn = fs.readFileSync(
  new URL("../components/StudentLearnPage.tsx", import.meta.url),
  "utf8",
);
const guided = fs.readFileSync(
  new URL("../components/StudentLearningSession.tsx", import.meta.url),
  "utf8",
);
const resolver = fs.readFileSync(
  new URL("../lib/student-material-version.ts", import.meta.url),
  "utf8",
);

test("student material version resolver prefers the assigned learning pin and falls back for old payloads", () => {
  assert.match(resolver, /return material\.learning_version \?\? material\.current_version/);
  assert.doesNotMatch(resolver, /fetch\(|api\(|method:\s*["']POST/);
  const assigned = { id: "assigned-version", version_no: 2, status: "parsed" };
  const current = { id: "latest-version", version_no: 4, status: "parsed" };
  assert.equal(studentMaterialVersion({ current_version: current, learning_version: assigned }), assigned);
  assert.equal(studentMaterialVersion({ current_version: current }), current);
  assert.equal(studentMaterialVersion({ current_version: current, learning_version: null }), current);
  assert.equal(studentMaterialVersion({ current_version: null }), null);
});

test("Learn and Guided display the same resolved version used by Guided session creation", () => {
  assert.match(learn, /import \{ studentMaterialVersion \} from "\.\.\/lib\/student-material-version"/);
  assert.match(learn, /type Material = \{[^\n]*learning_version\?/);
  assert.match(learn, /const version = studentMaterialVersion\(material\)/);
  assert.match(learn, /版本 \{version\?\.version_no \?\? "—"\}/);
  assert.doesNotMatch(learn, /material\.current_version\?\.version_no/);

  assert.match(guided, /import \{ studentMaterialVersion \} from "\.\.\/lib\/student-material-version"/);
  assert.match(guided, /type Material = \{[^\n]*learning_version\?/);
  assert.match(guided, /studentMaterialVersion\(data\[0\]\)\?\.id/);
  assert.match(guided, /const version = studentMaterialVersion\(material\)/);
  assert.match(guided, /className=\{version\?\.id === versionId \? "data-nav active"/);
  assert.match(guided, /setVersionId\(version\?\.id \?\? ""\)/);
  assert.match(guided, /版本 \{version\?\.version_no \?\? "—"\} · \{version\?\.status \?\? "不可用"\}/);
  const start = guided.slice(guided.indexOf("async function start()"), guided.indexOf("async function respond"));
  assert.match(start, /material_version_id: versionId/);
  assert.match(start, /payload: \{ material_version_id: versionId \}/);
  assert.doesNotMatch(guided, /material\.current_version\?\.(id|status)/);
});
