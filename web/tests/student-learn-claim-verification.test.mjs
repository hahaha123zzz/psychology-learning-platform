import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import {
  formatTutorClaimVerification,
  readTutorClaimVerification,
} from "../lib/tutor-claim-verification.ts";

const learn = fs.readFileSync(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const projection = fs.readFileSync(new URL("../lib/tutor-claim-verification.ts", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

const summary = (status, refusal_reason = null, supplemental_retrieval_attempts = 0, extra = {}) => ({
  status,
  refusal_reason,
  supplemental_retrieval_attempts,
  ...extra,
});

test("four safe status states use the required student-facing wording and include zero or one attempts", () => {
  const expected = [
    ["supported", "证据支持 · 补充检索次数：0"],
    ["partially-supported", "部分支持 · 补充检索次数：1 · 证据只支持其中一部分。", "claim_partially_supported", 1],
    ["contradicted", "发现反证 · 补充检索次数：0 · 发现与该主张不一致的证据。", "claim_contradicted", 0],
    ["unknown", "暂无法确认 · 补充检索次数：1 · 当前证据不足以确认。", "insufficient_evidence", 1],
  ];
  for (const [status, expectedText, reason = null, attempts = 0] of expected) {
    const parsed = readTutorClaimVerification(summary(status, reason, attempts));
    assert.ok(parsed);
    assert.equal(formatTutorClaimVerification(parsed), expectedText);
  }
});

test("null, invalid status/count/reason and arbitrary service strings fail closed", () => {
  for (const input of [
    null,
    undefined,
    [],
    summary("unknown-status"),
    summary("supported", null, true),
    summary("supported", null, -1),
    summary("supported", null, 2),
    summary("supported", null, 0.5),
    summary("unknown", "raw private server detail", 0),
    summary("unknown", "scope_mismatch", 0),
  ]) {
    assert.equal(readTutorClaimVerification(input), null);
  }
  assert.equal(readTutorClaimVerification(summary("supported", "raw private server detail")), null);
});

test("only allowlisted summary fields survive; scope, evidence and subclaims are inert private input", () => {
  const parsed = readTutorClaimVerification(summary("supported", null, 0, {
    scope: { user_id: "private-user", course_id: "private-course" },
    evidence_refs: ["private-evidence"],
    supported_subclaims: ["private claim text"],
    retrieval_payload: "private retrieval data",
  }));
  assert.deepEqual(parsed, {
    status: "supported",
    refusal_reason: null,
    supplemental_retrieval_attempts: 0,
  });
  const visible = formatTutorClaimVerification(parsed);
  assert.doesNotMatch(visible, /private-user|private-course|private-evidence|private claim text|private retrieval data/);
  assert.doesNotMatch(projection, /candidate\.(scope|evidence_refs|supported_subclaims|unsupported_subclaims|contradicted_subclaims|retrieval_payload)/);
});

test("live and replay SSE done events share one parser and only saved Tutor turns display the summary", () => {
  const doneHandler = learn.slice(learn.indexOf('if (eventData.event === "done")'), learn.indexOf('if (eventData.event === "error")'));
  assert.match(doneHandler, /eventData\.data\.saved === true[\s\S]*?readTutorClaimVerification\(eventData\.data\.claim_verification\)/);
  assert.match(doneHandler, /formatTutorClaimVerification\(claimVerification\)/);
  assert.match(doneHandler, /item\.role !== "tutor"/);
  assert.match(learn, /status: eventData\.data\.saved === true[\s\S]*claimVerificationText/);
  assert.match(api, /consumeSse<Record<string, unknown>>\(response, \(event\) =>[\s\S]*onEvent\(\{ event: event\.event, data: event\.data \}\)/);

  const live = readTutorClaimVerification(summary("partially-supported", "claim_partially_supported", 1));
  const replay = readTutorClaimVerification(summary("partially-supported", "claim_partially_supported", 1));
  assert.equal(formatTutorClaimVerification(live), formatTutorClaimVerification(replay));
});
