import type { LearningBlock } from "../../lib/learning-blocks";
import {
  getTeachingAssetFallbackReason,
  TEACHING_ASSET_FALLBACK_NOTICE,
} from "../../lib/teaching-assets-api";

function blockText(block: LearningBlock): string {
  return block.text ?? block.prompt ?? "此学习内容暂无可显示文本。";
}

function questionPrompt(block: LearningBlock): string {
  if (typeof block.prompt === "string" && block.prompt.trim()) return block.prompt;
  if (typeof block.text === "string" && block.text.trim()) return block.text;
  return "当前问题暂无可显示的题目内容。";
}

function assetFallback(block: LearningBlock): string {
  return typeof block.fallback_text === "string" && block.fallback_text.trim()
    ? block.fallback_text
    : "此教学资产暂不支持交互，请打开教材或继续文字学习。";
}

function TeachingAssetBlock({ block }: { block: LearningBlock }) {
  const content = block.content;
  const template = typeof block.template === "string" ? block.template : "";
  const reason = getTeachingAssetFallbackReason(template, content);
  const value = typeof content === "object" && content !== null && !Array.isArray(content)
    ? content as Record<string, unknown>
    : null;
  if (reason || !value) {
    return <article className="learning-block unknown-block teaching-asset-fallback" data-fallback-reason={reason ?? "content_unavailable"}>
      <h3>教学资产降级为文字</h3>
      <p role="status" aria-live="polite">{TEACHING_ASSET_FALLBACK_NOTICE}</p>
      <p>{assetFallback(block)}</p>
    </article>;
  }
  const title = value.title as string;
  const text = typeof value.text === "string" ? value.text : null;
  const items = Array.isArray(value.items)
    ? value.items.filter((item): item is string => typeof item === "string").slice(0, 20)
    : [];
  return <article className={`learning-block teaching-asset ${template}`} data-asset-template={template}>
    <h3>{title}</h3>
    {text && <p>{text}</p>}
    {items.length > 0 && <ul>{items.map((item, index) => <li key={`${block.id}-item-${index}`}>{item}</li>)}</ul>}
    {!text && items.length === 0 && <p>{assetFallback(block)}</p>}
    <details className="teaching-asset-text-fallback">
      <summary>展开纯文本说明</summary>
      <p>{assetFallback(block)}</p>
    </details>
  </article>;
}

export default function LearningBlockStream({ blocks }: { blocks: LearningBlock[] }) {
  return (
    <div className="learning-block-stream" data-block-count={blocks.length}>
      {blocks.map((block, index) => {
        if (block.type === "TaskCompletion") {
          return (
            <article className="learning-block task-completion" key={block.id}>
              <strong>本阶段已完成</strong>
              <p>{block.completion === "activity_completed" ? "活动完成，后续学习状态仍由证据持续更新。" : "可以继续下一步学习。"}</p>
            </article>
          );
        }
        if (block.type === "Transition") {
          return (
            <p className="learning-block transition" key={block.id}>
              下一步：{block.next_action ?? "继续当前任务"}
            </p>
          );
        }
        if (block.type === "Question") {
          const headingId = `learning-question-heading-${index}`;
          return (
            <section aria-labelledby={headingId} className="learning-block question-block" key={block.id}>
              <h3 id={headingId}>学习问题</h3>
              <p>{questionPrompt(block)}</p>
            </section>
          );
        }
        if (block.type === "Unknown") {
          const evidenceRefCount = block.evidence_refs?.length ?? 0;
          return (
            <article className="learning-block unknown-block" data-evidence-ref-count={evidenceRefCount} key={block.id}>
              <strong>暂不支持此内容</strong>
              <p>{blockText(block)}</p>
              {evidenceRefCount > 0 && <small>{evidenceRefCount} 个引用标识仅作为元数据，暂不可打开。</small>}
            </article>
          );
        }
        if (block.type === "TeachingAsset") {
          return <TeachingAssetBlock block={block} key={block.id} />;
        }
        return (
          <article className={`learning-block ${block.type.toLowerCase()}`} key={block.id}>
            <strong>{block.type === "TutorExplanation" ? "AI 教师" : "学习提示"}</strong>
            <p>{blockText(block)}</p>
          </article>
        );
      })}
    </div>
  );
}
