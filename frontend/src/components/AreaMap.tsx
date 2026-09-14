"use client";

import { memo, useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MetricThreeLayer, type MetricBarConfig } from "@/components/metricThreeLayer";
import {
  PolygonThreeLayer,
  hazardPolygonToShapes,
  zoningPolygonToShapes,
} from "@/components/polygonThreeLayer";
import { DomeScanLayer } from "@/components/domeScanLayer";
import type {
  DistributionPoint,
  HazardPolygonResult,
  MapPin,
  NearbyStation,
  ZoningMassingResult,
} from "@/lib/types";

/** hazard_polygons/zoning_massing 결과 — 원본 MLIT Polygon 3D 뷰.
 * distribution/areas 보다 우선한다(가장 구체적인 "역 하나 딥다이브" 모드). */
export type PolygonView =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult };

/** 좋고 나쁨이 없는 지표(백엔드 DIRECTIONLESS_METRICS 와 맞춘다) — 유동인구는
 * "많다/적다"이지 "좋다/나쁘다"가 아니다. 3D 막대에서는 이 지표들만
 * "높을수록 진하다(highIsIntense)"로 그리고, 나머지는 전부 percentile 이
 * 이미 "높을수록 좋다"인 지표라 "낮을수록 위험(highIsBad)"으로 그린다. */
const DIRECTIONLESS_METRICS = new Set(["daily_ridership", "residential_zone_ratio"]);

function barConfigFor(metric: string | undefined): MetricBarConfig {
  if (metric && DIRECTIONLESS_METRICS.has(metric)) {
    return { direction: "highIsIntense" };
  }
  return { direction: "highIsBad", particleThresholdPercentile: 20 };
}

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

export const AreaMap = memo(function AreaMap({
  areas,
  numbered = true,
  nearby = [],
  distribution = [],
  distributionMetric,
  polygonView = null,
  highlightStation = null,
}: {
  areas: MapPin[];
  numbered?: boolean;
  nearby?: NearbyStation[];
  /** metric_distribution 결과. 있으면 areas/nearby 대신 percentile 색점을 그린다. */
  distribution?: DistributionPoint[];
  /** distribution 이 어느 지표인지 — 3D 막대 방향(highIsBad/highIsIntense)을
   * 고르는 데만 쓴다. */
  distributionMetric?: string;
  /** hazard_polygons/zoning_massing 결과. 있으면 다른 모드보다 우선한다. */
  polygonView?: PolygonView | null;
  /** 돔+스캐닝 링 강조 표시할 역 — explain_area·rank_areas·hazard_polygons 등
   * 단일 역에 포커스가 생길 때 설정한다. null 이면 숨긴다. */
  highlightStation?: { lat: number; lon: number; radiusM?: number } | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const metricLayer = useRef<MetricThreeLayer | null>(null);
  const polygonLayer = useRef<PolygonThreeLayer | null>(null);
  const domeLayer = useRef<DomeScanLayer | null>(null);
  const pendingHighlight = useRef<{ lat: number; lon: number; radiusM?: number } | null>(null);
  // 마지막으로 pitch=45 카메라를 맞춘 역 — 같은 역이면 애니메이션을 반복 호출하지 않는다.
  const lastCameraStation = useRef<{ lat: number; lon: number } | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: TOKYO_CENTER,
      zoom: 10.5,
    });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    // 분포 조회(재해위험·유동인구 등)일 때 지표를 3D 막대+파티클로 얹는다 —
    // 기존 2D 색점 마커는 그대로 두고 시각 효과만 덧붙인다(metricThreeLayer.ts).
    instance.on("load", () => {
      const layer = new MetricThreeLayer();
      instance.addLayer(layer);
      metricLayer.current = layer;
      const polygons = new PolygonThreeLayer();
      instance.addLayer(polygons);
      polygonLayer.current = polygons;
      const dome = new DomeScanLayer();
      instance.addLayer(dome);
      domeLayer.current = dome;
      if (pendingHighlight.current) {
        dome.setStation(
          pendingHighlight.current.lat,
          pendingHighlight.current.lon,
          pendingHighlight.current.radiusM ?? 500,
        );
        pendingHighlight.current = null;
      }
    });
    map.current = instance;
    return () => {
      map.current?.remove();
      map.current = null;
      metricLayer.current = null;
      polygonLayer.current = null;
      domeLayer.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;

    markers.current.forEach((marker) => marker.remove());
    markers.current = [];

    // polygonView(원본 Polygon 3D 뷰)가 가장 구체적인 모드다 — 다른 걸 다
    // 지우고 이것만 그린다.
    if (polygonView) {
      metricLayer.current?.setPoints([], barConfigFor(undefined));
      const shapes =
        polygonView.kind === "hazard"
          ? polygonView.result.polygons.flatMap(hazardPolygonToShapes)
          : polygonView.result.polygons.flatMap(zoningPolygonToShapes);
      polygonLayer.current?.setShapes(shapes);

      const { lat, lon, name_ja, ward, radius_m } = polygonView.result;
      const pin = document.createElement("div");
      pin.className =
        "h-4 w-4 rounded-full border-2 border-white bg-rose-600 shadow-lg";
      const marker = new maplibregl.Marker({ element: pin })
        .setLngLat([lon, lat])
        .setPopup(new maplibregl.Popup({ offset: 10 }).setText(`${name_ja} (${ward})`))
        .addTo(instance);
      markers.current.push(marker);

      // pitch 를 건 뒤 곧바로 별도의 fitBounds/flyTo 를 부르면, 그 두 번째
      // 호출이 "아직 애니메이션 시작 전(=여전히 pitch 0)"인 transform 을
      // 기준으로 자기 카메라 파라미터를 잡아버려 pitch 가 조용히 원위치로
      // 취소된다(실측 — flyTo 뿐 아니라 fitBounds 도 마찬가지였다. 이전에
      // "fitBounds 로 바꾸면 된다"고 봤던 건 타이밍이 우연히 맞았던 것뿐이다).
      // 그래서 bounds 를 직접 계산해 pitch 와 함께 **단일 easeTo 호출**로
      // 합친다 — 취소할 두 번째 애니메이션 자체가 없다.
      const dlat = radius_m / 111_320;
      const dlon = radius_m / (111_320 * Math.cos((lat * Math.PI) / 180));
      const bounds = new maplibregl.LngLatBounds(
        [lon - dlon, lat - dlat],
        [lon + dlon, lat + dlat],
      );
      const camera = instance.cameraForBounds(bounds, { padding: 60, pitch: 60 });
      instance.easeTo({ ...camera, pitch: 60, duration: 600 });
      return;
    }
    polygonLayer.current?.setShapes([]);

    // 분포 모드가 있으면 그것만 그린다 — 순위 핀과 percentile 색점을 같이
    // 띄우면 "이 색이 순위인지 지표인지" 헷갈린다.
    if (distribution.length > 0) {
      metricLayer.current?.setPoints(distribution, barConfigFor(distributionMetric));
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

      // 3D 막대는 위에서 내려다보면 납작해 보인다 — 기울여야 높이가 보인다.
      // pitch 와 bounds-fit 을 분리 호출하면 두 번째 호출이 pitch 를
      // 조용히 취소한다(위 polygonView 분기와 같은 이유) — 한 번의 easeTo
      // 로 합친다.
      const distributionBounds = new maplibregl.LngLatBounds();
      distribution.forEach((point) => distributionBounds.extend([point.lon, point.lat]));
      const camera = instance.cameraForBounds(distributionBounds, { padding: 80, pitch: 60 });
      const zoom = Math.min(camera?.zoom ?? 14, 14);
      instance.easeTo({ ...camera, zoom, pitch: 60, duration: 600 });
      return;
    }

    // 분포 모드를 벗어나면 3D 막대도 지운다 — 안 지우면 다음 랭킹 지도 위에
    // 그대로 남는다.
    metricLayer.current?.setPoints([], barConfigFor(undefined));
    // highlightStation 이 있으면 아래에서 pitch=45 로 기울이므로 여기서 0으로 되돌리지 않는다.
    if (!highlightStation && instance.getPitch() !== 0) instance.easeTo({ pitch: 0, duration: 600 });

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

    // highlightStation(단일 역 포커스)이 있으면 pitch=45로 기울여 돔이 보이도록 한다.
    // fitBounds는 pitch 옵션 없으면 pitch=0으로 리셋하므로 cameraForBounds+easeTo로 통합.
    if (highlightStation) {
      const alreadyHere =
        lastCameraStation.current?.lat === highlightStation.lat &&
        lastCameraStation.current?.lon === highlightStation.lon;
      if (!alreadyHere) {
        lastCameraStation.current = highlightStation;
        const camera = instance.cameraForBounds(bounds, {
          padding: 80,
          maxZoom: areas.length === 1 ? 13.5 : 14,
        });
        instance.easeTo({ ...camera, pitch: 45, duration: 600 });
      }
    } else {
      lastCameraStation.current = null;
      instance.fitBounds(bounds, {
        padding: 80,
        maxZoom: areas.length === 1 ? 13.5 : 14,
        duration: 600,
      });
    }
  }, [areas, numbered, nearby, distribution, distributionMetric, polygonView, highlightStation]);

  useEffect(() => {
    if (highlightStation) {
      if (domeLayer.current) {
        domeLayer.current.setStation(
          highlightStation.lat,
          highlightStation.lon,
          highlightStation.radiusM ?? 500,
        );
      } else {
        // map load 전 — load 콜백에서 적용할 수 있도록 저장해 둔다.
        pendingHighlight.current = highlightStation;
      }
    } else {
      pendingHighlight.current = null;
      domeLayer.current?.clear();
    }
  }, [highlightStation]);

  return <div ref={container} className="h-full w-full" />;
});
