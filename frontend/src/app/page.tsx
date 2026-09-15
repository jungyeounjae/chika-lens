"use client";

import { useCallback, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AreaList } from "@/components/AreaList";
import { ChatMarkdown } from "@/components/ChatMarkdown";
import { streamChat } from "@/lib/chatStream";
import type {
  ExplainedArea,
  HazardPolygonResult,
  MapPin,
  MetricDistribution,
  NearbyStation,
  ParkPolygonResult,
  RankedArea,
  SchoolFacilitiesResult,
  ZoningMassingResult,
} from "@/lib/types";
import type { Overlay } from "@/components/AreaMap";

// maplibre 는 window 를 참조하므로 서버에서 렌더할 수 없다.
const AreaMap = dynamic(() => import("@/components/AreaMap").then((m) => m.AreaMap), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-neutral-100 dark:bg-neutral-900" />,
});

type Turn = {
  role: "user" | "assistant";
  text: string;
  // 툴이 실행되는 동안의 실시간 상태("역세권 순위 계산하는 중...").
  // text 가 채워지기 시작하면 더는 안 쓰인다 — 렌더 쪽에서 text 를 우선한다.
  status?: string;
  // 랭킹은 그 턴이 만든 것이지 화면 전체가 공유하는 값이 아니다 — 턴에
  // 직접 묶지 않으면 다음 턴 아래로 떠밀려 내려간다.
  areas?: RankedArea[];
};

const EXAMPLES = [
  "한식당이 많고 조용한 동네를 찾고 있어요",
  "아이 키우기 좋은 곳 추천해주세요",
  "신주쿠까지 30분 이내로 출퇴근할 수 있는 곳",
];

export default function Home() {
  const [turns, setTurns] = useState<Turn[]>([]);
  // 특정 역 조회는 랭킹이 아니다 — 순위 번호 없이 한 곳만 찍는다.
  const [pins, setPins] = useState<MapPin[]>([]);
  const [numbered, setNumbered] = useState(true);
  const [nearby, setNearby] = useState<NearbyStation[]>([]);
  // metric_distribution 결과. 있는 동안은 지도가 순위 핀 대신 percentile
  // 색점을 그린다 (AreaMap 참고).
  const [distribution, setDistribution] = useState<MetricDistribution | null>(null);
  // hazard_polygons/zoning_massing/park_polygons/school_facilities 결과들 —
  // 한 턴에 여러 개가 와도 전부 동시에 그린다(스펙
  // 2026-09-15-frontend-multi-layer-overlay-design.md).
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  // 돔+스캐닝 링 강조 역 — explain_area·rank_areas·hazard/zoning 포커스 시
  const [highlightStation, setHighlightStation] = useState<{ lat: number; lon: number; radiusM?: number } | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef(crypto.randomUUID());
  // 이번 턴이 만든 어시스턴트 메시지의 인덱스. `turns` 클로저가 아니라
  // 이 카운터로 계산해야 연속 호출에서도 어긋나지 않는다.
  const turnCount = useRef(0);

  const send = useCallback(
    async (message: string) => {
      if (!message.trim() || busy) return;
      setBusy(true);
      setError(null);
      setInput("");
      // 이 턴의 사용자 메시지는 turnCount.current, 어시스턴트 응답은 그 다음
      // 자리에 놓인다 — push 되기 전에 인덱스를 고정해 둔다.
      const assistantIndex = turnCount.current + 1;
      turnCount.current += 2;
      setTurns((prev) => [...prev, { role: "user", text: message }, { role: "assistant", text: "" }]);

      try {
        for await (const event of streamChat(sessionId.current, message)) {
          if (event.kind === "tool") {
            // 스펙 §5.4 — 툴 결과가 먼저 오므로 지도를 서술보다 먼저 그린다.
            const ranked = event.result as { areas?: RankedArea[] } | undefined;
            if (ranked?.areas) {
              setPins(ranked.areas);
              setNumbered(true);
              setNearby([]);
              setDistribution(null);
              setOverlays([]);
              // 1위 역에 돔+링 강조 표시
              const top = ranked.areas[0];
              if (top)
                setHighlightStation((prev) =>
                  prev?.lat === top.lat && prev?.lon === top.lon && prev?.radiusM === 500
                    ? prev
                    : { lat: top.lat, lon: top.lon, radiusM: 500 },
                );
              // 랭킹은 이 턴의 응답에 묶는다 — 전역에 두면 다음 턴이 생길 때
              // 화면 맨 아래로 떠밀려 방금 물은 것과 무관해 보인다.
              setTurns((prev) => {
                const next = [...prev];
                const target = next[assistantIndex];
                if (target) next[assistantIndex] = { ...target, areas: ranked.areas };
                return next;
              });
            }
            const single = event.result as Partial<ExplainedArea> | undefined;
            // hazard_polygons/zoning_massing 결과도 station_id+lat 모양이라
            // event.tool 로 gating 하지 않으면 오탐한다(실측) — explain_area만.
            if (event.tool === "explain_area" && single?.station_id && typeof single.lat === "number") {
              setPins([single as ExplainedArea]);
              setNumbered(false);
              setNearby(single.nearby ?? []);
              setDistribution(null);
              setOverlays([]);
              setHighlightStation((prev) =>
                prev?.lat === single.lat && prev?.lon === single.lon && prev?.radiusM === 500
                  ? prev
                  : { lat: single.lat!, lon: single.lon!, radiusM: 500 },
              );
            }
            const dist = event.result as Partial<MetricDistribution> | undefined;
            if (event.tool === "metric_distribution" && Array.isArray(dist?.points)) {
              // 분포 모드는 순위/단일 조회 핀과 동시에 뜨면 색의 의미가
              // 헷갈린다 — AreaMap이 distribution 이 있으면 그것만 그린다.
              setDistribution(dist as MetricDistribution);
              setOverlays([]);
              // 전체 분포를 보는 모드 — 단일 강조 없앤다
              setHighlightStation(null);
            }
            if (event.tool === "hazard_polygons" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const hazard = event.result as HazardPolygonResult;
              setDistribution(null);
              setOverlays((prev) => [...prev.filter((o) => o.kind !== "hazard"), { kind: "hazard", result: hazard }]);
              setHighlightStation((prev) =>
                prev?.lat === hazard.lat && prev?.lon === hazard.lon && prev?.radiusM === hazard.radius_m
                  ? prev
                  : { lat: hazard.lat, lon: hazard.lon, radiusM: hazard.radius_m },
              );
            }
            if (event.tool === "zoning_massing" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const zoning = event.result as ZoningMassingResult;
              setDistribution(null);
              setOverlays((prev) => [...prev.filter((o) => o.kind !== "zoning"), { kind: "zoning", result: zoning }]);
              setHighlightStation((prev) =>
                prev?.lat === zoning.lat && prev?.lon === zoning.lon && prev?.radiusM === zoning.radius_m
                  ? prev
                  : { lat: zoning.lat, lon: zoning.lon, radiusM: zoning.radius_m },
              );
            }
            if (event.tool === "park_polygons" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const park = event.result as ParkPolygonResult;
              setDistribution(null);
              setOverlays((prev) => [...prev.filter((o) => o.kind !== "park"), { kind: "park", result: park }]);
              setHighlightStation((prev) =>
                prev?.lat === park.lat && prev?.lon === park.lon && prev?.radiusM === park.radius_m
                  ? prev
                  : { lat: park.lat, lon: park.lon, radiusM: park.radius_m },
              );
            }
            if (event.tool === "school_facilities" && Array.isArray((event.result as { facilities?: unknown })?.facilities)) {
              const school = event.result as SchoolFacilitiesResult;
              setDistribution(null);
              setOverlays((prev) => [...prev.filter((o) => o.kind !== "facilities"), { kind: "facilities", result: school }]);
              setHighlightStation((prev) =>
                prev?.lat === school.lat && prev?.lon === school.lon && prev?.radiusM === school.radius_m
                  ? prev
                  : { lat: school.lat, lon: school.lon, radiusM: school.radius_m },
              );
            }
          } else if (event.kind === "status") {
            setTurns((prev) => {
              const next = [...prev];
              const target = next[assistantIndex];
              if (target) next[assistantIndex] = { ...target, status: event.text };
              return next;
            });
          } else if (event.kind === "text") {
            setTurns((prev) => {
              const next = [...prev];
              next[assistantIndex] = {
                ...next[assistantIndex],
                role: "assistant",
                text: next[assistantIndex].text + event.delta,
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
      <section className="relative h-2/5 shrink-0 md:order-2 md:h-full md:w-1/2">
        <AreaMap
          areas={pins}
          numbered={numbered}
          nearby={nearby}
          distribution={distribution?.points}
          distributionMetric={distribution?.metric}
          overlays={overlays}
          highlightStation={highlightStation}
        />
        {overlays.length > 0 && (
          <div className="absolute bottom-3 left-3 flex flex-col gap-2">
            {overlays.map((overlay, index) =>
              overlay.kind === "facilities" ? (
                <div
                  key={`facilities-${index}`}
                  className="rounded-lg border border-neutral-200 bg-white/95 px-3 py-2 text-xs shadow dark:border-neutral-700 dark:bg-neutral-900/95"
                >
                  <p className="font-medium">학교/보육시설 3D ({overlay.result.facilities.length}건)</p>
                  <p className="mt-0.5 text-neutral-500">
                    주황 = 유치원·보육시설, 파랑 = 초등·중학교. 반경 {Math.round(overlay.result.radius_m)}m 이내.
                  </p>
                </div>
              ) : (
                <div
                  key={`${overlay.kind}-${index}`}
                  className="rounded-lg border border-neutral-200 bg-white/95 px-3 py-2 text-xs shadow dark:border-neutral-700 dark:bg-neutral-900/95"
                >
                  <p className="font-medium">
                    {overlay.kind === "hazard"
                      ? "재해위험 3D (원본 구역)"
                      : overlay.kind === "zoning"
                        ? "용도지역 3D (원본 구역)"
                        : "공원 3D (OSM)"}
                  </p>
                  {overlay.kind === "zoning" && (
                    <p className="mt-0.5 text-neutral-500">높이는 실제 건축 높이 제한이 아니라 시각적 근사치입니다.</p>
                  )}
                  <p className="mt-1 text-[10px] text-neutral-500">{overlay.result.attribution}</p>
                </div>
              ),
            )}
          </div>
        )}
        {overlays.length === 0 && distribution && (
          <div className="absolute bottom-3 left-3 rounded-lg border border-neutral-200 bg-white/95 px-3 py-2 text-xs shadow dark:border-neutral-700 dark:bg-neutral-900/95">
            <p className="font-medium">
              {distribution.label}
              {distribution.is_ward_resolution && (
                <span className="ml-1 text-amber-600 dark:text-amber-500">구 단위</span>
              )}
            </p>
            <div className="mt-1 flex items-center gap-1.5">
              <span className="h-2 w-16 rounded-full bg-gradient-to-r from-red-600 via-yellow-400 to-green-600" />
            </div>
            <div className="mt-0.5 flex justify-between text-[10px] text-neutral-500">
              <span>하위권</span>
              <span>상위권(좋음)</span>
            </div>
          </div>
        )}
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

          {turns.map((turn, index) => {
            const placeholder =
              busy && index === turns.length - 1 ? (turn.status ?? "…") : "";
            return (
              <div key={index} className={turn.role === "user" ? "text-right" : ""}>
                {/* 사용자 입력은 평문으로 둔다 — 마크다운으로 해석할 이유가 없고,
                    자기가 쓴 별표가 사라지면 오히려 놀란다. */}
                {turn.role === "user" ? (
                  <div className="inline-block whitespace-pre-wrap rounded-2xl bg-neutral-900 px-3 py-2 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900">
                    {turn.text}
                  </div>
                ) : turn.text ? (
                  <>
                    <ChatMarkdown text={turn.text} />
                    {turn.areas && turn.areas.length > 0 && (
                      <div className="mt-2 text-left">
                        <AreaList areas={turn.areas} />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">
                    {turn.status ? <span className="animate-pulse">{placeholder}</span> : placeholder}
                  </div>
                )}
              </div>
            );
          })}

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
