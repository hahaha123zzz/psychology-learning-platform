import { api } from "./api";

export type LearningEventType =
  | "task_viewed"
  | "answer_submitted"
  | "tutor_responded"
  | "lab_trial_completed"
  | "feedback_submitted";

export type LearningEventSource = "tutor" | "assessment" | "practice" | "review" | "lab" | "system";

export type LearningEvent = {
  id: string;
  event_key: string;
  user_id: string;
  course_id: string;
  event_type: LearningEventType;
  source_type: LearningEventSource;
  source_ref: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  qualification_status: "pending" | "qualified" | "rejected" | "invalidated";
  qualification_reason: string | null;
  qualified_at: string | null;
};

export function appendLearningEvent(input: {
  event_key: string;
  course_id: string;
  event_type: LearningEventType;
  source_type: LearningEventSource;
  source_ref?: string;
  payload?: Record<string, unknown>;
  occurred_at?: string;
}) {
  return api<LearningEvent>("/learning-events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listMyLearningEvents(courseId: string, limit = 50) {
  return api<LearningEvent[]>(
    `/me/learning-events?course_id=${encodeURIComponent(courseId)}&limit=${limit}`,
  );
}
