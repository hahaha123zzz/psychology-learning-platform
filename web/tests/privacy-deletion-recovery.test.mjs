import assert from "node:assert/strict";
import test from "node:test";
import { createDeletionRecoveryMaterial } from "../lib/privacy-deletion.ts";

test("deletion recovery material is caller-minted, format-safe, and unpredictable", () => {
  const first = createDeletionRecoveryMaterial();
  const second = createDeletionRecoveryMaterial();
  assert.match(first.request_id, /^[0-7][0-9A-HJKMNP-TV-Z]{25}$/);
  assert.match(first.status_credential, /^[A-Za-z0-9_-]{43}$/);
  assert.notEqual(first.request_id, second.request_id);
  assert.notEqual(first.status_credential, second.status_credential);
});
