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
