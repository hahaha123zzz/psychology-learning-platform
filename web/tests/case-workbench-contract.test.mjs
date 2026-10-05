import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/StudentCaseWorkbench.tsx", import.meta.url),
  "utf8",
);

test("case drafts restore choice and reasoning while native controls remain keyboard/touch operable", () => {
  assert.match(source, /<input\s+type="radio"/);
  assert.match(source, /<label[\s\S]*?<input\s+type="radio"[\s\S]*?setSelected\(option\.key\)/);
  assert.match(source, /setSelected\(resumable\.response\?\.selected_confound \?\? ""\)/);
  assert.match(source, /setReasoning\(resumable\.response\?\.reasoning \?\? ""\)/);
  assert.match(source, /setDesignChange\(resumable\.response\?\.design_change \?\? ""\)/);
  assert.match(source, /draft:\s*true/);
  assert.match(source, /setNotice\(message\(reason\)\)/);
});

test("case submit failure preserves editable values and exposes a retryable error", () => {
  assert.match(source, /catch \(reason\) \{[\s\S]*?setNotice\(message\(reason\)\);[\s\S]*?finally/);
  assert.match(source, /role=\{draftState === "error" \|\| workspaceFailed \? "alert" : "status"\}/);
  assert.match(source, /onClick=\{\(\) => void submit\(\)\}/);
  assert.match(source, /重试提交/);
  assert.match(source, /服务器已保存此案例；已恢复服务端提交结果/);
  assert.match(source, /不评价推理正确性/);
  assert.match(source, /reasoning_completion_points/);
  assert.doesNotMatch(source, /理由一致性 \{/);
});

test("initial network failure retains successful reads and requires an accessible reload before starting", () => {
  assert.match(source, /Promise\.allSettled\(/);
  assert.match(source, /catalogResult\.status === "fulfilled"/);
  assert.match(source, /sessionsResult\.status === "fulfilled"/);
  assert.match(source, /重试读取案例/);
  assert.match(source, /尚未确认当前课程已有的案例会话；读取成功前不能开始新案例/);
  assert.match(source, /!workspaceLoaded \? \(/);
  assert.match(source, /type="button" onClick=\{retryWorkspaceLoad\}/);
  assert.match(source, /function retryWorkspaceLoad\(\) \{\s*setWorkspaceFailed\(false\);\s*setNotice\("正在重新读取案例与已有会话…"\)/);
  assert.match(source, /draftState === "error" \|\| workspaceFailed \? "alert" : "status"/);
});
