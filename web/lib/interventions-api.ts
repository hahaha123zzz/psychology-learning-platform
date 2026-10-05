import { api, idempotencyKey } from "./api";

export type InterventionStatus =
  | "draft"
  | "scheduled"
  | "active"
  | "completed"
  | "evaluated"
  | "archived";
export type InterventionActivity = "reteach" | "practice_set" | "mini_lab" | "discussion" | "review";

export type Intervention = {
  id: string;
  course_id: string;
  class_id: string | null;
  created_by: string;
  approved_by: string | null;
  title: string;
  activity_type: InterventionActivity;
  target_snapshot: Record<string, unknown>;
  plan: Record<string, unknown>;
  status: InterventionStatus;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  evaluated_at: string | null;
  outcome: Record<string, unknown> | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type InterventionRun = {
  id: string;
  intervention_id: string;
  course_id: string;
  user_id: string;
  status: "scheduled" | "in_progress" | "paused" | "completed" | "cancelled";
  started_at: string | null;
  completed_at: string | null;
  outcome: Record<string, unknown> | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type TeacherObservation = {
  id: string;
  course_id: string;
  class_id: string | null;
  student_id: string;
  teacher_id: string;
  observation_type: "misconception" | "strategy" | "support_need" | "progress";
  note: string;
  evidence_refs: string[];
  qualification_status: "pending" | "qualified" | "rejected";
  review_decision: "pending" | "accepted" | "rejected";
  verification_status: "pending" | "qualified" | "rejected" | "invalidated";
  verification_event_id: string | null;
  verification_qualification_id: string | null;
  verification_evidence_ids: string[];
  verification_algorithm_version: string | null;
  verification_reason: string | null;
  verified_at: string | null;
  source_evidence_status: "valid" | "invalidated" | "unavailable";
  algorithm_version: string | null;
  reviewed_by: string | null;
  review_reason: string | null;
  reviewed_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type TeacherObservationRevalidationCandidate = {
  learning_event_id: string;
  qualification_id: string;
  event_type: string;
  source_type: string;
  occurred_at: string;
  qualified_at: string;
  evidence_count: number;
  evidence_ids: string[];
};

export function listTeacherObservations(courseId: string, status?: TeacherObservation["qualification_status"]) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return api<TeacherObservation[]>(`/courses/${courseId}/observations${query}`);
}

export function createTeacherObservation(
  courseId: string,
  input: Pick<TeacherObservation, "student_id" | "class_id" | "observation_type" | "note" | "evidence_refs">,
  requestKey = idempotencyKey(),
) {
  return api<TeacherObservation>(`/courses/${courseId}/observations`, {
    method: "POST",
    headers: { "Idempotency-Key": requestKey },
    body: JSON.stringify(input),
  });
}

export function revalidateTeacherObservation(
  courseId: string,
  observation: TeacherObservation,
  learningEventId: string,
) {
  return api<TeacherObservation>(
    `/courses/${courseId}/observations/${observation.id}/revalidate`,
    {
      method: "POST",
      body: JSON.stringify({
        version: observation.version,
        learning_event_id: learningEventId,
      }),
    },
  );
}

export function listTeacherObservationRevalidationCandidates(
  courseId: string,
  observationId: string,
) {
  return api<TeacherObservationRevalidationCandidate[]>(
    `/courses/${courseId}/observations/${observationId}/revalidation-candidates`,
  );
}

export function reviewTeacherObservation(
  courseId: string,
  observation: TeacherObservation,
  decision: "qualified" | "rejected",
  reason: string,
) {
  return api<TeacherObservation>(
    `/courses/${courseId}/observations/${observation.id}/review`,
    {
      method: "POST",
      body: JSON.stringify({ version: observation.version, decision, reason }),
    },
  );
}

export function listInterventions(courseId: string) {
  return api<Intervention[]>(`/courses/${courseId}/interventions`);
}

export function createIntervention(
  courseId: string,
  input: Pick<Intervention, "title" | "activity_type" | "class_id" | "target_snapshot" | "plan">,
) {
  return api<Intervention>(`/courses/${courseId}/interventions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function scheduleIntervention(courseId: string, intervention: Intervention) {
  return api<Intervention>(`/courses/${courseId}/interventions/${intervention.id}/schedule`, {
    method: "POST",
    body: JSON.stringify({
      version: intervention.version,
      scheduled_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    }),
  });
}

export function transitionIntervention(
  courseId: string,
  intervention: Intervention,
  action: "start" | "complete",
) {
  return api<Intervention>(
    `/courses/${courseId}/interventions/${intervention.id}/${action}`,
    { method: "POST", body: JSON.stringify({ version: intervention.version }) },
  );
}

export function evaluateIntervention(
  courseId: string,
  intervention: Intervention,
  outcome: Record<string, unknown>,
) {
  return api<Intervention>(`/courses/${courseId}/interventions/${intervention.id}/evaluate`, {
    method: "POST",
    body: JSON.stringify({ version: intervention.version, outcome }),
  });
}

export function dispatchIntervention(
  courseId: string,
  intervention: Intervention,
  userIds: string[],
) {
  return api<{ intervention: Intervention; runs: InterventionRun[] }>(
    `/courses/${courseId}/interventions/${intervention.id}/dispatch`,
    {
      method: "POST",
      body: JSON.stringify({ version: intervention.version, user_ids: userIds }),
    },
  );
}

export function listInterventionRuns(courseId: string, interventionId: string) {
  return api<InterventionRun[]>(
    `/courses/${courseId}/interventions/${interventionId}/runs`,
  );
}

export function listStudentInterventionRuns(courseId?: string) {
  return api<InterventionRun[]>(
    courseId ? `/student/intervention-runs?course_id=${encodeURIComponent(courseId)}` : "/student/intervention-runs",
  );
}

export function transitionStudentInterventionRun(
  run: InterventionRun,
  action: "start" | "complete",
  outcome?: Record<string, unknown>,
) {
  return api<InterventionRun>(`/student/intervention-runs/${run.id}/${action}`, {
    method: "POST",
    body: JSON.stringify({ version: run.version, ...(outcome ? { outcome } : {}) }),
  });
}
