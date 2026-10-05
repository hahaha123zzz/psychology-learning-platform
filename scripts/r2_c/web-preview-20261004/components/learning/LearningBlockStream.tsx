import type { LearningBlock } from "../../lib/learning-blocks";

function blockText(block: LearningBlock): string {
  return block.text ?? block.prompt ?? "此学习内容暂无可显示文本。";
}

function assetFallback(block: LearningBlock): string {
  return typeof block.fallback_text === "string" && block.fallback_text.trim()
    ? block.fallback_text
    : "此教学资产暂不支持交互，请打开教材或继续文字学习。";
}

function assetContent(block: LearningBlock): Record<string, unknown> | null {
  const value = block.content;
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function TeachingAssetBlock({ block }: { block: LearningBlock }) {
  const content = assetContent(block);
  const template = typeof block.template === "string" ? block.template : "";
  const title = content && typeof content.title === "string" ? content.title : "教学资产";
  const text = content && typeof content.text === "string" ? content.text : null;
  const items = content && Array.isArray(content.items)
    ? content.items.filter((item): item is string => typeof item === "string").slice(0, 20)
    : [];
  const supported = new Set(["explanation", "comparison", "variable_map", "table", "focus"]);
  if (!content || !supported.has(template)) {
    return <article className="learning-block unknown-block">
      <h3>教学资产降级为文字</h3>
      <p>{assetFallback(block)}</p>
    </article>;
  }
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
      {blocks.map((block) => {
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
        if (block.type === "Unknown") {
          return (
            <article className="learning-block unknown-block" key={block.id}>
              <strong>暂不支持此内容</strong>
              <p>{blockText(block)}</p>
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
