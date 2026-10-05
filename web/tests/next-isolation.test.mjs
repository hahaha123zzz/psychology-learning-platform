import assert from "node:assert/strict";
import test from "node:test";
import { resolveNextRuntimeConfig } from "../lib/next-runtime-config.mjs";

test("Next 保留原预览默认代理和构建目录", () => {
  assert.deepEqual(resolveNextRuntimeConfig({}), {
    apiProxyOrigin: "http://127.0.0.1:8000",
    distDir: ".next",
  });
});

test("独立 Web 可绑定专属 API 和构建目录", () => {
  assert.deepEqual(
    resolveNextRuntimeConfig({
      PSYCHOLOGY_API_PROXY_TARGET: "http://127.0.0.1:8201/",
      PSYCHOLOGY_NEXT_DIST_DIR: ".next-r2-a",
    }),
    {
      apiProxyOrigin: "http://127.0.0.1:8201",
      distDir: ".next-r2-a",
    },
  );
});

test("代理目标只允许无路径、无凭据的 HTTP(S) origin", () => {
  for (const target of [
    "file:///tmp/api",
    "http://user:secret@127.0.0.1:8201",
    "http://127.0.0.1:8201/api",
    "http://127.0.0.1:8201/?token=secret",
  ]) {
    assert.throws(() => resolveNextRuntimeConfig({ PSYCHOLOGY_API_PROXY_TARGET: target }));
  }
});

test("构建目录拒绝绝对路径、穿越和子目录", () => {
  for (const distDir of ["..", "../outside", "nested/.next", "C:\\build", ".next-r2-unregistered"]) {
    assert.throws(() => resolveNextRuntimeConfig({ PSYCHOLOGY_NEXT_DIST_DIR: distDir }));
  }
});
