export type ServerSentEvent<T> = {
  event: string;
  data: T;
  id?: string;
};

function parseFrame<T>(frame: string): ServerSentEvent<T> | null {
  const fields = frame.split(/\r?\n/);
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const field of fields) {
    if (!field || field.startsWith(":")) continue;
    const separator = field.indexOf(":");
    const name = separator === -1 ? field : field.slice(0, separator);
    const value = separator === -1 ? "" : field.slice(separator + 1).replace(/^ /, "");
    if (name === "event") event = value || "message";
    if (name === "id") id = value;
    if (name === "data") data.push(value);
  }
  if (data.length === 0) return null;
  try {
    return { event, id, data: JSON.parse(data.join("\n")) as T };
  } catch {
    return null;
  }
}

export async function consumeSse<T>(
  response: Response,
  onEvent: (event: ServerSentEvent<T>) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) throw new Error("SSE 响应没有可读取的内容");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const cancelOnAbort = () => {
    void reader.cancel(signal?.reason).catch(() => undefined);
  };
  signal?.addEventListener("abort", cancelOnAbort, { once: true });
  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel(signal.reason);
        return;
      }
      const { done, value } = await reader.read();
      pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const frames = pending.split(/\r?\n\r?\n/);
      pending = frames.pop() ?? "";
      for (const frame of frames) {
        const parsed = parseFrame<T>(frame);
        if (parsed) onEvent(parsed);
      }
      if (done) {
        const parsed = parseFrame<T>(pending);
        if (parsed) onEvent(parsed);
        return;
      }
    }
  } catch (error) {
    if (!signal?.aborted) await reader.cancel(error).catch(() => undefined);
    throw error;
  } finally {
    signal?.removeEventListener("abort", cancelOnAbort);
    reader.releaseLock();
  }
}
