export const LEARNING_BLOCK_SCHEMA_VERSION = "learning-block.v1" as const;

export type LearningBlockType =
  | "TutorExplanation"
  | "Question"
  | "Hint"
  | "WorkedExample"
  | "TeachingAsset"
  | "EvidencePrompt"
  | "Feedback"
  | "Correction"
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
  "Correction",
  "Transition",
  "TaskCompletion",
]);
const UNKNOWN_TEXT_MAX_LENGTH = 4_000;
const UNKNOWN_EVIDENCE_REF_LIMIT = 12;
const UNKNOWN_EVIDENCE_REF_MAX_LENGTH = 128;
const UNKNOWN_BLOCK_NOTICE = "此学习内容暂不支持显示，请返回当前任务或打开教材。";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedPlainText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .trim();
  return normalized ? normalized.slice(0, UNKNOWN_TEXT_MAX_LENGTH) : null;
}

function fallbackText(candidate: Record<string, unknown> | null): string {
  for (const field of ["text", "prompt", "completion"] as const) {
    const value = boundedPlainText(candidate?.[field]);
    if (value) return value;
  }
  return UNKNOWN_BLOCK_NOTICE;
}

function fallbackEvidenceRefs(candidate: Record<string, unknown> | null): string[] {
  if (!Array.isArray(candidate?.evidence_refs)) return [];
  return candidate.evidence_refs
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim().slice(0, UNKNOWN_EVIDENCE_REF_MAX_LENGTH))
    .filter(Boolean)
    .slice(0, UNKNOWN_EVIDENCE_REF_LIMIT);
}

function isMalformedKnownBlock(candidate: Record<string, unknown>): boolean {
  for (const field of ["text", "prompt", "completion", "next_action"] as const) {
    if (field in candidate && typeof candidate[field] !== "string") return true;
  }
  if ("evidence_refs" in candidate && !Array.isArray(candidate.evidence_refs)) return true;
  if (Array.isArray(candidate.evidence_refs) && candidate.evidence_refs.some((value) => typeof value !== "string")) return true;
  return false;
}

function unknownBlock(index: number, candidate: Record<string, unknown> | null): LearningBlock {
  return {
    id: `unknown-${index}`,
    type: "Unknown",
    text: fallbackText(candidate),
    evidence_refs: fallbackEvidenceRefs(candidate),
  };
}

export function normalizeLearningBlocks(value: unknown): LearningBlock[] {
  if (!Array.isArray(value)) return [];
  return value.map((candidate, index) => {
    if (!isRecord(candidate)) return unknownBlock(index, null);
    const validId = typeof candidate.id === "string" && Boolean(candidate.id.trim());
    const knownType = typeof candidate.type === "string" && KNOWN_TYPES.has(candidate.type as LearningBlockType);
    if (!validId || !knownType || isMalformedKnownBlock(candidate)) return unknownBlock(index, candidate);
    return {
      ...candidate,
      type: candidate.type,
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
