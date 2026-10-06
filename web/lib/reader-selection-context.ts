export const readerSelectionContextKey = "student-learn-selection-context";

type ReaderSelectionContext = {
  course_id: string;
  evidence_pointer_id: string;
};

const subscribers = new Set<() => void>();

function parseStoredContext(raw: string | null): ReaderSelectionContext | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const value = parsed as Record<string, unknown>;
    const keys = Object.keys(value).sort();
    if (
      keys.length !== 2 ||
      keys[0] !== "course_id" ||
      keys[1] !== "evidence_pointer_id" ||
      typeof value.course_id !== "string" ||
      !value.course_id.trim() ||
      typeof value.evidence_pointer_id !== "string" ||
      !value.evidence_pointer_id.trim()
    ) {
      return null;
    }
    return {
      course_id: value.course_id,
      evidence_pointer_id: value.evidence_pointer_id,
    };
  } catch {
    return null;
  }
}

function notifySubscribers() {
  for (const subscriber of subscribers) subscriber();
}

export function subscribeReaderSelectionContext(subscriber: () => void) {
  subscribers.add(subscriber);
  return () => subscribers.delete(subscriber);
}

export function readReaderSelectionPointerId(courseId: string): string {
  if (typeof window === "undefined" || !courseId) return "";
  try {
    const value = parseStoredContext(window.sessionStorage.getItem(readerSelectionContextKey));
    return value?.course_id === courseId ? value.evidence_pointer_id : "";
  } catch {
    return "";
  }
}

export function persistReaderSelection(courseId: string, evidencePointerId: string) {
  if (typeof window === "undefined" || !courseId.trim() || !evidencePointerId.trim()) return;
  try {
    window.sessionStorage.setItem(readerSelectionContextKey, JSON.stringify({
      course_id: courseId,
      evidence_pointer_id: evidencePointerId,
    } satisfies ReaderSelectionContext));
  } catch {
    return;
  }
  notifySubscribers();
}

export function clearReaderSelection() {
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(readerSelectionContextKey);
    } catch {
      // 页面上下文仍可使用内存快照；受限存储不能阻断关闭 Reader。
    }
  }
  notifySubscribers();
}

export function clearReaderSelectionForCourse(courseId: string) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.sessionStorage.getItem(readerSelectionContextKey);
    if (raw === null) return;
    const value = parseStoredContext(raw);
    if (value?.course_id === courseId) return;
    window.sessionStorage.removeItem(readerSelectionContextKey);
    notifySubscribers();
  } catch {
    // 无法读取或清理时，getSnapshot 仍会对当前课程返回空选择。
  }
}
