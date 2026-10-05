import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("TeachingAsset edits create immutable versions and expose keyboard text fallback", () => {
  const editor = read("../components/TeachingAssetEditor.tsx");
  const renderer = read("../components/learning/LearningBlockStream.tsx");

  assert.match(editor, /复制并编辑为新版本/);
  assert.match(editor, /createTeachingAsset\(courseId/);
  assert.match(editor, /原版本不会被覆盖/);
  assert.match(editor, /无障碍文本预览/);
  assert.match(renderer, /<details className="teaching-asset-text-fallback">/);
  assert.match(renderer, /<summary>展开纯文本说明<\/summary>/);
  assert.match(renderer, /assetFallback\(block\)/);
  assert.match(renderer, /TEACHING_ASSET_FALLBACK_NOTICE/);
  assert.match(renderer, /data-fallback-reason=\{reason/);
  assert.match(renderer, /aria-live="polite"/);
  assert.doesNotMatch(renderer, /dangerouslySetInnerHTML/);
  const assetApi = read("../lib/teaching-assets-api.ts");
  assert.match(assetApi, /template_unsupported/);
  assert.match(assetApi, /device_capability_unavailable/);
  assert.match(assetApi, /content_unavailable/);
  const miniLabStyles = read("../design-system/mini-lab.css");
  assert.match(miniLabStyles, /\.teaching-asset-text-fallback summary:focus-visible/);
  assert.match(miniLabStyles, /outline-offset: 3px/);
});

test("Mini Lab exposes service checkpoint recovery and marks the engineering fixture", () => {
  const panel = read("../components/StudentMiniLabPanel.tsx");
  const runtime = read("../components/learning/MiniLabRuntime.tsx");

  assert.match(panel, /getActiveMiniLab\(courseId\)/);
  assert.match(panel, /setRecoveryGeneration/);
  assert.match(panel, /工程 fixture/);
  assert.match(runtime, /恢复已保存阶段/);
  assert.match(runtime, /未确认的试次不会作为完成记录/);
  assert.match(runtime, /本次试次未保存/);
  assert.match(panel, /作废当前实验/);
  assert.match(panel, /session\.status === "invalidated"/);
  const labApi = read("../lib/mini-lab-api.ts");
  assert.match(labApi, /expected_version: session\.version/);
  assert.match(labApi, /idempotency_key: idempotencyKey/);
  const miniLabStyles = read("../design-system/mini-lab.css");
  assert.match(miniLabStyles, /\.mini-lab-invalidation button:focus-visible/);
  assert.match(miniLabStyles, /\.mini-lab-invalidation textarea:focus-visible/);
  assert.match(miniLabStyles, /\.jspsych-btn:focus-visible/);
  assert.match(miniLabStyles, /\.jspsych-btn-group-grid\s*\{[^}]*auto-fit/s);
  assert.match(miniLabStyles, /max-width: 100%/);
  assert.match(miniLabStyles, /@media \(max-width: 560px\)/);
});
