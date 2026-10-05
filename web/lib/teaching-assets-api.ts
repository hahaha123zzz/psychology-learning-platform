import { api } from "./api";

export type TeachingAsset = {
  id: string;
  course_id: string;
  release_id: string | null;
  asset_key: string;
  version_no: number;
  template: TeachingAssetTemplate;
  status: string;
  content: Record<string, unknown>;
  fallback_text: string;
  evidence_refs: string[];
  allowed_actions: string[];
  version: number;
};

export type TeachingAssetTemplate = "explanation" | "comparison" | "variable_map" | "table" | "focus";

export const TEACHING_ASSET_FALLBACK_NOTICE =
  "当前设备/模板无法呈现交互内容，已切换纯文本说明";

export type TeachingAssetFallbackReason =
  | "template_unsupported"
  | "device_capability_unavailable"
  | "content_unavailable";

export function getTeachingAssetFallbackReason(
  template: string | undefined,
  content: unknown,
  supportedTemplates: readonly string[] = ["explanation", "comparison", "variable_map", "table", "focus"],
): TeachingAssetFallbackReason | null {
  const allowedTemplates = ["explanation", "comparison", "variable_map", "table", "focus"];
  if (!template || !allowedTemplates.includes(template)) return "template_unsupported";
  if (!supportedTemplates.includes(template)) return "device_capability_unavailable";
  if (typeof content !== "object" || content === null || Array.isArray(content)) {
    return "content_unavailable";
  }
  const value = content as Record<string, unknown>;
  const hasText = typeof value.text === "string" && value.text.trim().length > 0;
  const hasItems = Array.isArray(value.items) && value.items.some(
    (item) => typeof item === "string" && item.trim().length > 0,
  );
  if (typeof value.title !== "string" || !value.title.trim() || (!hasText && !hasItems)) {
    return "content_unavailable";
  }
  return null;
}

export function listTeachingAssets(courseId: string) {
  return api<TeachingAsset[]>(`/courses/${courseId}/teaching-assets`);
}

export function createTeachingAsset(courseId: string, input: {
  asset_key: string;
  template: TeachingAssetTemplate;
  content: Record<string, unknown>;
  fallback_text: string;
  evidence_refs: string[];
  allowed_actions: string[];
}) {
  return api<TeachingAsset>(`/courses/${courseId}/teaching-assets`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function publishTeachingAsset(courseId: string, asset: TeachingAsset, releaseId: string) {
  return api<TeachingAsset>(`/courses/${courseId}/teaching-assets/${asset.id}/publish`, {
    method: "POST",
    body: JSON.stringify({ version: asset.version, release_id: releaseId }),
  });
}
