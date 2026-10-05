import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { consumeSse } from "../lib/sse.ts";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const encoder = new TextEncoder();

test("SSE parser preserves complete events split across chunks and flushes final EOF frame", async () => {
  const bytes = encoder.encode(
    'event: delta\nid: 3\ndata: {"text":"实验心理"}\n\nevent: done\ndata: {"saved":true}',
  );
  const response = new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(bytes.slice(0, 17));
      controller.enqueue(bytes.slice(17, 46));
      controller.enqueue(bytes.slice(46));
      controller.close();
    },
  }));
  const events = [];

  await consumeSse(response, (event) => events.push(event));

  assert.deepEqual(events, [
    { event: "delta", id: "3", data: { text: "实验心理" } },
    { event: "done", id: undefined, data: { saved: true } },
  ]);
  assert.equal(response.body.locked, false);
});

test("SSE abort and callback failure cancel the reader and release the stream lock", async () => {
  let abortCancelled = false;
  const abortResponse = new Response(new ReadableStream({
    cancel() { abortCancelled = true; },
  }));
  const abort = new AbortController();
  const pending = consumeSse(abortResponse, () => undefined, abort.signal);
  abort.abort();
  await pending;
  assert.equal(abortCancelled, true);
  assert.equal(abortResponse.body.locked, false);

  let callbackCancelled = false;
  const callbackResponse = new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('event: delta\ndata: {"text":"x"}\n\n'));
    },
    cancel() { callbackCancelled = true; },
  }));
  await assert.rejects(
    consumeSse(callbackResponse, () => { throw new Error("consumer failed"); }),
    /consumer failed/,
  );
  assert.equal(callbackCancelled, true);
  assert.equal(callbackResponse.body.locked, false);
});

test("Tutor retries reuse a pending turn ID and retain the prompt until saved completion", () => {
  const api = read("../lib/api.ts");
  const learnPage = read("../components/StudentLearnPage.tsx");

  assert.match(api, /client_turn_id: clientTurnId/);
  assert.match(api, /event\.data\.saved !== true/);
  assert.match(api, /if \(!completed\)/);
  assert.match(learnPage, /pendingTurn = useRef/);
  assert.match(learnPage, /previous\?\.sessionId === activeSession && previous\.content === content/);
  assert.match(learnPage, /setQuestion\(content\)/);
  assert.match(learnPage, /setQuestion\(""\)/);
});
