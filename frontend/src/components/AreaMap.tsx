"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DistributionPoint, MapPin, NearbyStation } from "@/lib/types";

const TOKYO_CENTER: [number, number] = [139.7, 35.69];

/** OpenStreetMap 래스터 타일.
 *
 * Google Maps JS API 를 쓰지 않는 이유는 비용이다 — 지도 로드마다 과금되는
 * 별도 SKU인데, 우리가 지도에서 필요한 것은 핀 다섯 개뿐이다.
 * 데이터 수집에 쓰는 Google 예산을 화면에까지 늘릴 이유가 없다.
 */
const OSM_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

/** percentile(0~100, 높을수록 좋다/안전하다로 통일된 값)을 빨강-노랑-초록으로.
 *
 * raw_value 가 아니라 percentile 로 칠한다 — 시세·재해위험·감점 상권은
 * raw 가 클수록 나쁜데 percentile 은 이미 뒤집혀 있다. raw로 칠하면
 * 감점 지표에서 색이 거꾸로 나간다.
 */
function colorFromPercentile(percentile: number): string {
  const hue = Math.max(0, Math.min(100, percentile)) * 1.2; // 0=빨강 ~ 120=초록
  return `hsl(${hue}, 72%, 42%)`;
}

export function AreaMap({
  areas,
  numbered = true,
  nearby = [],
  distribution = [],
}: {
  areas: MapPin[];
  numbered?: boolean;
  nearby?: NearbyStation[];
  /** metric_distribution 결과. 있으면 areas/nearby 대신 percentile 색점을 그린다. */
  distribution?: DistributionPoint[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: TOKYO_CENTER,
      zoom: 10.5,
    });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    map.current = instance;
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;

    markers.current.forEach((marker) => marker.remove());
    markers.current = [];

    // 분포 모드가 있으면 그것만 그린다 — 순위 핀과 percentile 색점을 같이
    // 띄우면 "이 색이 순위인지 지표인지" 헷갈린다.
    if (distribution.length > 0) {
      distribution.forEach((point) => {
        const dot = document.createElement("div");
        const background = point.is_missing ? "#a3a3a3" : colorFromPercentile(point.percentile);
        dot.style.cssText =
          `background:${background};width:22px;height:22px;border-radius:9999px;` +
          "border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);";
        const valueLine = point.is_missing
          ? "데이터 없음"
          : `${point.raw_value ?? "-"} · 상위 ${(100 - point.percentile).toFixed(0)}%`;
        const marker = new maplibregl.Marker({ element: dot })
          .setLngLat([point.lon, point.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 14 }).setText(
              `${point.name_ja} (${point.ward}) · ${valueLine}`,
            ),
          )
          .addTo(instance);
        markers.current.push(marker);
      });

      const distributionBounds = new maplibregl.LngLatBounds();
      distribution.forEach((point) => distributionBounds.extend([point.lon, point.lat]));
      instance.fitBounds(distributionBounds, { padding: 80, maxZoom: 14, duration: 600 });
      return;
    }

    if (areas.length === 0) return;

    areas.forEach((area, index) => {
      const pin = document.createElement("div");
      pin.className =
        "flex h-7 w-7 items-center justify-center rounded-full border-2 " +
        "border-white bg-rose-600 text-xs font-bold text-white shadow-lg";
      // 단일 역 조회에는 순위가 없다 — 번호 대신 점을 찍는다.
      pin.textContent = numbered ? String(index + 1) : "";

      const marker = new maplibregl.Marker({ element: pin })
        .setLngLat([area.lon, area.lat])
        .setPopup(
          // 종합 점수는 비교 기준이 있을 때만 온다 — 없으면 이름만 찍는다.
          new maplibregl.Popup({ offset: 18 }).setText(
            [
              numbered ? `${index + 1}. ` : "",
              `${area.name_ja} (${area.ward})`,
              area.score === undefined ? "" : ` ${area.score.toFixed(1)}점`,
            ].join(""),
          ),
        )
        .addTo(instance);
      markers.current.push(marker);
    });

    // 주변 역은 작은 회색 점으로. 주역과 구분되어야 "역이 하나뿐"이 읽힌다.
    nearby.forEach((station) => {
      const dot = document.createElement("div");
      dot.className =
        "h-3 w-3 rounded-full border border-white bg-neutral-500 shadow";
      const marker = new maplibregl.Marker({ element: dot })
        .setLngLat([station.lon, station.lat])
        .setPopup(
          new maplibregl.Popup({ offset: 10 }).setText(
            `${station.name_ja} · 약 ${Math.round(station.distance_m / 100) * 100}m` +
              (station.lines.length ? ` · ${station.lines.join(", ")}` : ""),
          ),
        )
        .addTo(instance);
      markers.current.push(marker);
    });

    const bounds = new maplibregl.LngLatBounds();
    areas.forEach((area) => bounds.extend([area.lon, area.lat]));
    nearby.forEach((station) => bounds.extend([station.lon, station.lat]));
    // 핀이 하나면 fitBounds 가 최대 배율까지 당긴다. 동네가 보이는 정도로 둔다.
    instance.fitBounds(bounds, {
      padding: 80,
      maxZoom: areas.length === 1 ? 13.5 : 14,
      duration: 600,
    });
  }, [areas, numbered, nearby, distribution]);

  return <div ref={container} className="h-full w-full" />;
}
