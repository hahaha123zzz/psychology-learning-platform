import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import Module from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { normalizeLearningBlocks } from "../lib/learning-blocks.ts";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const renderer = fs.readFileSync(
  new URL("../components/learning/LearningBlockStream.tsx", import.meta.url),
  "utf8",
);
const guidedSession = fs.readFileSync(
  new URL("../components/StudentLearningSession.tsx", import.meta.url),
  "utf8",
);

test("unknown blocks become bounded local plain-text fallbacks with only string evidence IDs", () => {
  const input = {
    id: "server-controlled-id",
    type: "FutureBlock",
    text: `  ${"plain <b>text</b> ".repeat(400)}  `,
    prompt: "a lower-priority prompt",
    completion: "a lower-priority completion",
    evidence_refs: ["  pointer-1  ", 42, "", ...Array.from({ length: 14 }, (_, index) => `pointer-${index + 2}`)],
    allowed_actions: ["RESPOND_TASK", "OPEN_EVIDENCE"],
    html: "<script>document.body.innerHTML = 'unsafe'</script>",
    javascript: "alert('unsafe')",
    content: { hidden: "field" },
  };

  const [fallback] = normalizeLearningBlocks([input]);
  assert.equal(fallback.id, "unknown-0");
  assert.equal(fallback.type, "Unknown");
  assert.equal(fallback.text?.length, 4_000);
  assert.ok(fallback.text?.startsWith("plain <b>text</b>"));
  assert.deepEqual(fallback.evidence_refs, ["pointer-1", ...Array.from({ length: 11 }, (_, index) => `pointer-${index + 2}`)]);
  assert.ok(fallback.evidence_refs?.every((ref) => typeof ref === "string" && ref.length <= 128));
  assert.deepEqual(Object.keys(fallback).sort(), ["evidence_refs", "id", "text", "type"]);
});

test("malformed blocks use text, prompt, then completion and drop executable or action fields", () => {
  const blocks = normalizeLearningBlocks([
    { type: "TutorExplanation", id: "   ", text: "", prompt: "  prompt fallback  ", completion: "completion fallback", allowed_actions: ["RESPOND_TASK"] },
    { id: "invalid-text", type: "TutorExplanation", text: { html: "<script>run()</script>" }, evidence_refs: ["safe-id", 44] },
    null,
  ]);

  assert.deepEqual(blocks.map(({ id, type, text }) => ({ id, type, text })), [
    { id: "unknown-0", type: "Unknown", text: "prompt fallback" },
    { id: "unknown-1", type: "Unknown", text: "此学习内容暂不支持显示，请返回当前任务或打开教材。" },
    { id: "unknown-2", type: "Unknown", text: "此学习内容暂不支持显示，请返回当前任务或打开教材。" },
  ]);
  assert.deepEqual(blocks[1].evidence_refs, ["safe-id"]);
  assert.ok(blocks.every((block) => !Object.hasOwn(block, "allowed_actions") && !Object.hasOwn(block, "html")));
});

test("known blocks retain their existing schema and content", () => {
  const known = { id: "known-1", type: "TutorExplanation", text: "Synthetic known block", evidence_refs: ["pointer-1"], allowed_actions: ["OPEN_EVIDENCE"] };
  assert.deepEqual(normalizeLearningBlocks([known]), [known]);
});

test("Question blocks keep prompt content and render as a readable, non-interactive question section", () => {
  const [question] = normalizeLearningBlocks([{
    id: "question-1",
    type: "Question",
    prompt: "Synthetic question prompt",
    text: "Secondary description",
  }]);
  assert.equal(question.type, "Question");
  assert.equal(question.prompt, "Synthetic question prompt");

  const questionBranch = renderer.match(/if \(block\.type === "Question"\)[\s\S]*?\n        }/);
  assert.ok(questionBranch, "renderer has a dedicated Question branch");
  assert.match(questionBranch[0], /<section aria-labelledby=\{headingId\}/);
  assert.match(questionBranch[0], /<h3 id=\{headingId\}>学习问题<\/h3>/);
  assert.match(questionBranch[0], /<p>\{questionPrompt\(block\)\}<\/p>/);
  assert.doesNotMatch(questionBranch[0], /<input\b|<textarea\b|<button\b|<a\b|<form\b|onSubmit=|onClick=|api\(/);
  assert.match(renderer, /function questionPrompt\(block: LearningBlock\)[\s\S]*block\.prompt[\s\S]*block\.text/);
  assert.match(renderer, /const questionHeadingId = useId\(\)/);
  assert.match(renderer, /const headingId = `\$\{questionHeadingId\}-question-\$\{index\}`/);
  assert.match(guidedSession, /<form className="composer" onSubmit=\{respond\}>/);
  assert.match(guidedSession, /`\/student\/learning\/tasks\/\$\{learning\.id\}\/respond`/);
});

test("ordinary TutorExplanation remains a separate readable explanation block", () => {
  const explanationBranch = renderer.match(/return \(\s*<article className=\{`learning-block \$\{block\.type\.toLowerCase\(\)\}`\}[\s\S]*?\n        \);/);
  assert.ok(explanationBranch, "ordinary explanation uses the existing generic explanation renderer");
  assert.match(explanationBranch[0], /block\.type === "TutorExplanation" \? "AI 教师" : "学习提示"/);
  assert.match(explanationBranch[0], /\{blockText\(block\)\}/);
  assert.doesNotMatch(explanationBranch[0], /学习问题|questionPrompt/);
});

test("separate LearningBlockStream instances produce unique Question heading targets", () => {
  const rendererPath = fileURLToPath(new URL("../components/learning/LearningBlockStream.tsx", import.meta.url));
  const source = fs.readFileSync(rendererPath, "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText.replace(
    'require("../../lib/teaching-assets-api")',
    '({ getTeachingAssetFallbackReason: () => null, TEACHING_ASSET_FALLBACK_NOTICE: "synthetic fallback" })',
  );
  const rendererModule = new Module(rendererPath);
  rendererModule.filename = rendererPath;
  rendererModule.paths = Module._nodeModulePaths(path.dirname(rendererPath));
  rendererModule._compile(compiled, rendererPath);
  const LearningBlockStream = rendererModule.exports.default;
  const block = { id: "question-instance", type: "Question", prompt: "Synthetic prompt" };
  const markup = renderToStaticMarkup(React.createElement("div", null,
    React.createElement(LearningBlockStream, { blocks: [block] }),
    React.createElement(LearningBlockStream, { blocks: [block] }),
  ));
  const ids = [...markup.matchAll(/<h3 id="([^"]+)">学习问题<\/h3>/g)].map((match) => match[1]);
  assert.equal(ids.length, 2);
  assert.notEqual(ids[0], ids[1]);
  assert.ok(ids.every((id) => markup.includes(`aria-labelledby="${id}"`)));
});

test("unknown block rendering exposes text and inert reference count without actions or links", () => {
  const unknownBranch = renderer.match(/if \(block\.type === "Unknown"\)[\s\S]*?\n        }/);
  assert.ok(unknownBranch, "renderer has an explicit Unknown fallback branch");
  assert.match(unknownBranch[0], /\{blockText\(block\)\}/);
  assert.match(unknownBranch[0], /data-evidence-ref-count=\{evidenceRefCount\}/);
  assert.match(unknownBranch[0], /仅作为元数据，暂不可打开/);
  assert.doesNotMatch(unknownBranch[0], /<a\b|href=|onClick=|allowed_actions|evidence_refs\.map/);
  assert.doesNotMatch(renderer, /dangerouslySetInnerHTML/);
});
