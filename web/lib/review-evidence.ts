import type { LearningEvent } from "./learning-events";

export type ReviewQualificationStatus = "qualified" | "rejected" | "invalidated" | "pending";

export function isReviewEvidenceQualified(status: ReviewQualificationStatus): boolean {
  return status === "qualified";
}

export async function waitForReviewQualification(
  eventId: string,
  courseId: string,
  listEvents: () => Promise<LearningEvent[]>,
  options: { attempts?: number; intervalMs?: number; sleep?: (milliseconds: number) => Promise<void> } = {},
): Promise<ReviewQualificationStatus> {
  const attempts = Math.max(1, options.attempts ?? 4);
  const intervalMs = Math.max(0, options.intervalMs ?? 300);
  const sleep = options.sleep ?? ((milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds)));

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const event = (await listEvents()).find((item) => item.id === eventId && item.course_id === courseId);
    if (event?.qualification_status === "qualified" || event?.qualification_status === "rejected" || event?.qualification_status === "invalidated") {
      return event.qualification_status;
    }
    if (attempt + 1 < attempts) await sleep(intervalMs);
  }
  return "pending";
}
