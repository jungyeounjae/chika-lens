"use client";

import { useCallback, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AreaList } from "@/components/AreaList";
import { streamChat } from "@/lib/chatStream";
import type { ExplainedArea, MapPin, RankedArea } from "@/lib/types";

// maplibre 는 window 를 참조하므로 서버에서 렌더할 수 없다.
const AreaMap = dynamic(() => import("@/components/AreaMap").then((m) => m.AreaMap), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-neutral-100 dark:bg-neutral-900" />,
});

type Turn = { role: "user" | "assistant"; text: string };

const EXAMPLES = [
  "한식당이 많고 조용한 동네를 찾고 있어요",
  "아이 키우기 좋은 곳 추천해주세요",
  "신주쿠까지 30분 이내로 출퇴근할 수 있는 곳",
];

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [areas, setAreas] = useState<RankedArea[]>([]);
  // 특정 역 조회는 랭킹이 아니다 — 순위 번호 없이 한 곳만 찍는다.
  const [pins, setPins] = useState<MapPin[]>([]);
  const [numbered, setNumbered] = useState(true);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef(crypto.randomUUID());

  const send = useCallback(
    async (message: string) => {
      if (!message.trim() || busy) return;
      setBusy(true);
      setError(null);
      setInput("");
      setTurns((prev) => [...prev, { role: "user", text: message }, { role: "assistant", text: "" }]);

      try {
        for await (const event of streamChat(sessionId.current, message)) {
          if (event.kind === "tool") {
            // 스펙 §5.4 — 툴 결과가 먼저 오므로 지도를 서술보다 먼저 그린다.
            const ranked = event.result as { areas?: RankedArea[] } | undefined;
            if (ranked?.areas) {
              setAreas(ranked.areas);
              setPins(ranked.areas);
              setNumbered(true);
            }
            const single = event.result as Partial<ExplainedArea> | undefined;
            if (single?.station_id && typeof single.lat === "number") {
              setAreas([]);
              setPins([single as ExplainedArea]);
              setNumbered(false);
            }
          } else if (event.kind === "text") {
            setTurns((prev) => {
              const next = [...prev];
              next[next.length - 1] = {
                role: "assistant",
                text: next[next.length - 1].text + event.delta,
              };
              return next;
            });
          } else if (event.kind === "error") {
            setError(event.message);
          }
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "서버에 연결하지 못했습니다");
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  return (
    <main className="flex h-dvh flex-col md:flex-row">
      {/* 지도 — 모바일에서는 위쪽 40%, 데스크톱에서는 오른쪽 절반 */}
      <section className="h-2/5 shrink-0 md:order-2 md:h-full md:w-1/2">
        <AreaMap areas={pins} numbered={numbered} />
      </section>

      <section className="flex min-h-0 flex-1 flex-col border-neutral-200 md:order-1 md:w-1/2 md:border-r dark:border-neutral-800">
        <header className="border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
          <h1 className="font-semibold">Chika Lens</h1>
          <p className="text-xs text-neutral-500">도쿄 23구 · 489개 역세권을 한국인 관점으로</p>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {turns.length === 0 && (
            <div className="space-y-2">
              <p className="text-sm text-neutral-500">이렇게 물어보세요</p>
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => void send(example)}
                  className="block w-full rounded-lg border border-neutral-200 px-3 py-2 text-left text-sm hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
                >
                  {example}
                </button>
              ))}
            </div>
          )}

          {turns.map((turn, index) => (
            <div key={index} className={turn.role === "user" ? "text-right" : ""}>
              <div
                className={
                  turn.role === "user"
                    ? "inline-block rounded-2xl bg-neutral-900 px-3 py-2 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "whitespace-pre-wrap text-sm leading-relaxed"
                }
              >
                {turn.text || (busy && index === turns.length - 1 ? "…" : "")}
              </div>
            </div>
          ))}

          <AreaList areas={areas} />

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
              {error}
            </p>
          )}
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
          className="flex gap-2 border-t border-neutral-200 p-3 dark:border-neutral-800"
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            // IME 조합 중 Enter 는 한자·한글 변환 확정이지 전송이 아니다.
            // 막지 않으면 일본어·한국어 입력에서 문장이 도중에 잘려 나간다.
            onKeyDown={(event) => {
              if (event.key === "Enter" && event.nativeEvent.isComposing) {
                event.preventDefault();
              }
            }}
            placeholder="어떤 곳을 찾으세요?"
            disabled={busy}
            className="min-w-0 flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
          >
            보내기
          </button>
        </form>
      </section>
    </main>
  );
}
