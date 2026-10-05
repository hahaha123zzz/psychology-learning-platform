export const LEARNING_BLOCK_SCHEMA_VERSION = "learning-block.v1" as const;

export type LearningBlockType =
  | "TutorExplanation"
  | "Question"
  | "Hint"
  | "WorkedExample"
  | "TeachingAsset"
  | "EvidencePrompt"
  | "Feedback"
  | "Transition"
  | "TaskCompletion"
  | "Unknown";

export type LearningBlock = {
  id: string;
  schema_version?: string;
  type: LearningBlockType | string;
  text?: string;
  prompt?: string;
  completion?: string;
  next_action?: string;
  evidence_refs?: string[];
  allowed_actions?: string[];
  state?: string;
  hint_level?: number;
  [key: string]: unknown;
};

const KNOWN_TYPES = new Set<LearningBlockType>([
  "TutorExplanation",
  "Question",
  "Hint",
  "WorkedExample",
  "TeachingAsset",
  "EvidencePrompt",
  "Feedback",
  "Transition",
  "TaskCompletion",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function normalizeLearningBlocks(value: unknown): LearningBlock[] {
  if (!Array.isArray(value)) return [];
  return value.map((candidate, index) => {
    if (!isRecord(candidate) || typeof candidate.id !== "string" || typeof candidate.type !== "string") {
      return {
        id: `unknown-${index}`,
        type: "Unknown",
        text: "此学习内容暂不支持显示，请返回当前任务或打开教材。",
      };
    }
    return {
      ...candidate,
      type: KNOWN_TYPES.has(candidate.type as LearningBlockType)
        ? candidate.type
        : "Unknown",
    } as LearningBlock;
  });
}

export function legacyLearningBlocks(
  sessionId: string,
  stateVersion: number,
  message: string,
): LearningBlock[] {
  return [
    {
      id: `${sessionId}:${stateVersion}:legacy-explanation`,
      schema_version: LEARNING_BLOCK_SCHEMA_VERSION,
      type: "TutorExplanation",
      text: message,
      evidence_refs: [],
      allowed_actions: ["OPEN_EVIDENCE"],
    },
  ];
}
