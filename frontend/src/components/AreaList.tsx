"use client";

import type { RankedArea } from "@/lib/types";

const yen = (value: number) => `${value.toLocaleString("ja-JP")}엔`;

export function AreaList({ areas }: { areas: RankedArea[] }) {
  if (areas.length === 0) return null;

  return (
    <ol className="space-y-2">
      {areas.map((area, index) => (
        <li
          key={area.station_id}
          className="rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900"
        >
          <div className="flex items-baseline gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-600 text-[11px] font-bold text-white">
              {index + 1}
            </span>
            {/* 역명은 일본어 그대로 — 사용자가 이 표기로 부동산 사이트를 검색하고 표를 산다 */}
            <span className="font-semibold">{area.name_ja}</span>
            <span className="text-xs text-neutral-500">{area.ward}</span>
            <span className="ml-auto text-sm tabular-nums">{area.score.toFixed(1)}점</span>
          </div>

          <div className="mt-1.5 text-xs text-neutral-600 dark:text-neutral-400">
            월세 {area.rent_yen === null ? "데이터 없음" : yen(area.rent_yen)}
            {area.commute_uncertain && " · 통근시간 확인 필요"}
          </div>

          <ul className="mt-2 flex flex-wrap gap-1.5">
            {area.top_drivers.map((driver) => (
              <li
                key={driver.metric}
                className="rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] dark:bg-neutral-800"
                title={driver.is_ward_resolution ? "이 지표는 구 단위입니다" : undefined}
              >
                {driver.label} 상위 {Math.round(driver.top_percent)}%
                {/* 스펙 §3.2 — 구 단위 지표는 반드시 명시한다 */}
                {driver.is_ward_resolution && (
                  <span className="ml-1 text-amber-600 dark:text-amber-500">구 단위</span>
                )}
                {driver.is_missing && (
                  <span className="ml-1 text-neutral-400">데이터 없음</span>
                )}
              </li>
            ))}
          </ul>

          {area.missing_metrics.length > 0 && (
            <p className="mt-1.5 text-[11px] text-neutral-400">
              데이터 없음: {area.missing_metrics.map((m) => m.label).join(", ")}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
