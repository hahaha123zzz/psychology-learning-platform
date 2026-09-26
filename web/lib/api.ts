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
