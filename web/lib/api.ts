export type ApiEnvelope<T> = { data: T; meta?: { request_id?: string; server_time?: string; next_cursor?: string | null; has_more?: boolean } };
type ErrorEnvelope = { error?: { message?: string; details?: unknown; code?: string; retryable?: boolean } };
type XhrEnvelope<T> = { data?: T } & ErrorEnvelope;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: unknown,
    public readonly code?: string,
    public readonly retryable = false,
  ) { super(message); }
}

async function unwrap<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(
    response.status,
    body?.error?.message ?? "请求失败，请稍后重试",
    body?.error?.details,
    body?.error?.code,
    Boolean(body?.error?.retryable),
  );
  return body.data as T;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return unwrap<T>(await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" }));
}

export function idempotencyKey(): string { return crypto.randomUUID(); }

export function uploadForm<T>(path: string, body: FormData, onProgress: (percent: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/v1${path}`);
    request.withCredentials = true;
    request.setRequestHeader("Idempotency-Key", idempotencyKey());
    request.upload.onprogress = event => {
      if (event.lengthComputable && event.total > 0) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onerror = () => reject(new ApiError(0, "上传连接中断。当前版本不支持断点续传，请重新上传。", undefined, "UPLOAD_NETWORK_ERROR", true));
    request.onload = () => {
      let envelope: XhrEnvelope<T> | null = null;
      try { envelope = JSON.parse(request.responseText) as XhrEnvelope<T>; } catch { /* 响应不是 JSON */ }
      if (request.status >= 200 && request.status < 300 && envelope?.data !== undefined) {
        onProgress(100);
        resolve(envelope.data);
        return;
      }
      const error = envelope?.error;
      reject(new ApiError(request.status, error?.message ?? "上传失败，请稍后重试", error?.details, error?.code, Boolean(error?.retryable)));
    };
    request.send(body);
  });
}

type UploadSession = {
  upload_session_id: string;
  status: string;
  original_filename: string;
  size_bytes: number;
  part_size_bytes: number;
  total_parts: number;
  completed_parts: number[];
};

type UploadPartUrl = { part_number: number; size_bytes: number; upload_url: string };

export async function uploadMaterialResumable(
  courseId: string,
  input: { title: string; material_type: string; file: File },
  onProgress: (percent: number, detail: string) => void,
): Promise<{ material_id: string; version_id: string; status: string }> {
  const storageKey = `material-upload:${courseId}:${input.file.name}:${input.file.size}`;
  let session: UploadSession | null = null;
  const stored = window.localStorage.getItem(storageKey);
  if (stored) {
    try {
      const candidate = await api<UploadSession>(`/upload-sessions/${stored}`);
      if (candidate.status === "uploading") session = candidate;
      else window.localStorage.removeItem(storageKey);
    } catch { window.localStorage.removeItem(storageKey); }
  }
  if (!session) {
    session = await api<UploadSession>(`/courses/${courseId}/upload-sessions`, {
      method: "POST",
      body: JSON.stringify({
        title: input.title,
        material_type: input.material_type,
        filename: input.file.name,
        size_bytes: input.file.size,
      }),
    });
    window.localStorage.setItem(storageKey, session.upload_session_id);
  }
  const completed = new Set(session.completed_parts);
  for (let number = 1; number <= session.total_parts; number += 1) {
    if (completed.has(number)) continue;
    const part = await api<UploadPartUrl>(`/upload-sessions/${session.upload_session_id}/parts/${number}/url`, { method: "POST" });
    const start = (number - 1) * session.part_size_bytes;
    const blob = input.file.slice(start, start + part.size_bytes);
    onProgress(Math.round((completed.size / session.total_parts) * 100), `正在上传第 ${number}/${session.total_parts} 个分片…`);
    let response: Response | null = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      response = await fetch(part.upload_url, { method: "PUT", body: blob });
      if (response.ok) break;
    }
    if (!response?.ok) throw new ApiError(0, "分片上传未完成，已保存进度；网络恢复后重新选择同一文件即可继续。", undefined, "UPLOAD_PART_NETWORK_ERROR", true);
    const etag = response.headers.get("ETag");
    if (!etag) throw new ApiError(502, "对象存储未返回 ETag，无法安全确认分片。", undefined, "UPLOAD_PART_ETAG_MISSING", true);
    await api(`/upload-sessions/${session.upload_session_id}/parts/${number}`, {
      method: "PUT", body: JSON.stringify({ etag, size_bytes: blob.size }),
    });
    completed.add(number);
    onProgress(Math.round((completed.size / session.total_parts) * 100), `已完成 ${completed.size}/${session.total_parts} 个分片`);
  }
  const result = await api<{ material_id: string; version_id: string; status: string }>(`/upload-sessions/${session.upload_session_id}/complete`, { method: "POST" });
  window.localStorage.removeItem(storageKey);
  onProgress(100, "上传与完整性校验完成。");
  return result;
}

export type ChatEvent = { event: string; data: Record<string, unknown> };

export async function streamChatTurn(sessionId: string, content: string, onEvent: (event: ChatEvent) => void): Promise<void> {
  const response = await fetch(`/api/v1/chat/sessions/${sessionId}/turns`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, client_turn_id: crypto.randomUUID() }),
  });
  if (!response.ok || !response.body) await unwrap(response);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  while (true) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const frames = pending.split("\n\n"); pending = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1] ?? "message";
      const raw = frame.match(/^data: (.+)$/m)?.[1];
      if (raw) onEvent({ event, data: JSON.parse(raw) as Record<string, unknown> });
    }
    if (done) break;
  }
}
