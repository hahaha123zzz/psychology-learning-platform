import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const guided = fs.readFileSync(new URL("../components/StudentLearningSession.tsx", import.meta.url), "utf8");
const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");

test("restored guided task links to its own course Learn route without sending task content", () => {
  assert.match(guided, /const courseForLearn = learning\?\.course_id \?\? courseId/);
  assert.match(guided, /courseForLearn && <Link className="secondary-button" href=\{`\/student\/courses\/\$\{encodeURIComponent\(courseForLearn\)\}\/learn`\}>打开课程教材与学习助手<\/Link>/);
  assert.match(guided, /window\.sessionStorage\.setItem\("student-learning-task", session\.id\)/);
  assert.doesNotMatch(guided, /打开课程教材与学习助手[^\n]*\?session_id|href=\{`[^`]*student\/courses[^`]*\$\{[^}]*tutor_message/);
});

test("course Learn offers a keyboard-accessible return route and leaves task recovery in sessionStorage", () => {
  assert.match(learn, /import Link from "next\/link"/);
  const returnLink = learn.match(/<Link className="secondary-button" href="\/student\/learning">返回引导学习任务<\/Link>/)?.[0];
  assert.ok(returnLink, "course Learn should render a normal keyboard-focusable anchor");
  assert.match(guided, /window\.sessionStorage\.getItem\("student-learning-task"\)/);
  assert.doesNotMatch(returnLink, /onClick|sessionStorage/);
});

test("synthetic Home→guided task→Learn browser script is read-only after login", () => {
  const browser = fs.readFileSync(new URL("./student-guided-courseqa-handoff-browser.cjs", import.meta.url), "utf8");
  assert.match(browser, /UI011_TASK_ID/);
  assert.match(browser, /UI011_EMAIL/);
  assert.match(browser, /UI011_PASSWORD/);
  assert.match(browser, /继续当前任务|恢复当前任务/);
  assert.match(browser, /打开课程教材与学习助手/);
  assert.match(browser, /返回引导学习任务/);
  assert.match(browser, /\/api\/v1\/student\/learning\/tasks\//);
  assert.match(browser, /state_version/);
  assert.match(browser, /businessWrites/);
  assert.match(browser, /只允许读取和页面导航，不触发业务写/);
  assert.doesNotMatch(browser, /\/chat\/sessions|\/turns|method:\s*["']POST["']/);
});
