import type { ChatEvent } from "./types";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

/** `POST /chat` 의 SSE 스트림을 이벤트로 풀어낸다.
 *
 * EventSource 를 못 쓴다 — 그쪽은 GET 만 지원하는데 대화 본문은 POST 로 보낸다.
 * 그래서 fetch 스트림을 직접 파싱한다.
 */
export async function* streamChat(
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  });

  if (!response.body) {
    yield { kind: "error", code: "no_body", message: "응답 본문이 없다" };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette 는 CRLF 로 줄을 끝낸다. 정규화하지 않으면 "\n\n" 을 찾는
    // 프레임 분할이 영원히 실패한다 — \r\n\r\n 안에는 연속된 \n 이 없다.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    // SSE 는 빈 줄로 프레임을 나눈다.
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const parsed = parseFrame(frame);
      if (parsed) yield parsed;
    }
  }
}

function parseFrame(frame: string): ChatEvent | null {
  let name = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!name || !data) return null;

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data);
  } catch {
    return null;
  }

  switch (name) {
    case "text":
      return { kind: "text", delta: String(payload.delta ?? "") };
    case "tool":
      return { kind: "tool", tool: String(payload.tool ?? ""), result: payload.result };
    case "done":
      return { kind: "done", remainingToday: Number(payload.remaining_today ?? 0) };
    case "error":
      return {
        kind: "error",
        code: String(payload.code ?? "unknown"),
        message: String(payload.message ?? ""),
      };
    default:
      return null;
  }
}
