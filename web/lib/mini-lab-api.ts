import { api } from "./api";
import type { MiniLabDefinition, MiniLabResult } from "./mini-lab/jspsych-adapter";

export type MiniLabCatalogItem = MiniLabDefinition & {
  lab_key: string;
  knowledge_point?: string;
};

export type MiniLabSession = {
  id: string;
  course_id: string;
  lab_key: string;
  definition_snapshot: MiniLabDefinition;
  status: string;
  phase: string;
  trial_data: MiniLabResult["trial_data"];
  derived_measure: {
    qualification_status?: string;
    qualification_reason?: string | null;
    explanation_complete?: boolean;
    transfer_complete?: boolean;
  } | null;
  version: number;
  started_at: string;
  completed_at: string | null;
  invalidation_reason: string | null;
  invalidated_at: string | null;
  created_at: string;
  updated_at: string;
};

export function listMiniLabs(courseId: string) {
  return api<MiniLabCatalogItem[]>(`/student/labs/catalog?course_id=${encodeURIComponent(courseId)}`);
}

export function createMiniLab(courseId: string, labKey: string) {
  return api<MiniLabSession>("/student/labs", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, lab_key: labKey }),
  });
}

export function getActiveMiniLab(courseId: string) {
  return api<MiniLabSession | null>(
    `/student/labs/active?course_id=${encodeURIComponent(courseId)}`,
  );
}

export function saveMiniLabProgress(
  session: MiniLabSession,
  trialData: MiniLabResult["trial_data"],
) {
  return api<MiniLabSession>(`/student/labs/${session.id}/trials`, {
    method: "POST",
    body: JSON.stringify({ version: session.version, trial_data: trialData }),
  });
}

export function submitMiniLabResult(session: MiniLabSession, result: MiniLabResult) {
  return api<MiniLabSession>(`/student/labs/${session.id}/result`, {
    method: "POST",
    body: JSON.stringify({ ...result, version: session.version }),
  });
}

export function invalidateMiniLab(
  session: MiniLabSession,
  reason: string,
  idempotencyKey: string,
) {
  return api<MiniLabSession>(`/student/labs/${session.id}/invalidate`, {
    method: "POST",
    body: JSON.stringify({
      expected_version: session.version,
      idempotency_key: idempotencyKey,
      reason,
    }),
  });
}
