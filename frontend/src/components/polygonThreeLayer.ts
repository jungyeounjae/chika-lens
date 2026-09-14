"use client";

import * as maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Map as MapLibreMap } from "maplibre-gl";
import { getSharedRenderer } from "@/components/sharedThreeRenderer";
import type { GeoJsonGeometry, HazardPolygon, ZoningPolygon } from "@/lib/types";

export type ExtrudedShape = {
  /** 외곽 링만 쓴다(구멍 무시) — MLIT 재해·용도지역 폴리곤은 이 지역에서
   * 대체로 단순 다각형이라, 구멍(섬 모양 제외구역) 처리 없이도 충분하다. */
  ring: [number, number][]; // [lon, lat][]
  heightM: number;
  color: THREE.Color;
  opacity: number;
  /** true면 render 루프에서 맥박 opacity 애니메이션을 건다(Red Zone 전용). */
  pulse?: boolean;
};

/** exterior ring만 뽑는다 — Polygon은 coordinates[0], MultiPolygon은 각
 * 폴리곤의 coordinates[0]. */
export function exteriorRings(geometry: GeoJsonGeometry): [number, number][][] {
  if (geometry.type === "Polygon") {
    return [geometry.coordinates[0] as [number, number][]];
  }
  return geometry.coordinates.map((polygon) => polygon[0] as [number, number][]);
}

const MAX_HAZARD_HEIGHT_M = 60.0; // severity(0~1, 클수록 위험) 를 시각적 압출 높이(m)로.
const SEDIMENT_YELLOW_HEIGHT_M = 15.0; // Yellow Zone — 낮고 완만하게
const SEDIMENT_RED_HEIGHT_M = 40.0; // Red Zone — 높고 날카롭게
//: 가장 흔한 등급(예: 홍수 레벨1, 0~0.5m)은 severity가 낮아(1/6≈0.17),
//: 높이·색 모두 severity에 정직하게 비례시키면 옅은 색 10m 높이 상자가 돼
//: 지도 배경에 묻혀 거의 안 보인다(실사용에서 확인). 최소 높이를 둬서
//: "약하게라도 위험이 있다"가 화면에서도 보이게 한다.
const MIN_HAZARD_HEIGHT_M = 25.0;

//: 레이어별 색상 축(hue, 0~1). sediment 는 Yellow/Red 존을 그대로 쓰므로
//: (등급표를 몰라도 색으로 바로 읽힌다) 여기 없다 — 아래 sedimentColor 참고.
const HAZARD_HUE: Partial<Record<HazardPolygon["layer"], number>> = {
  flood: 0.6, // 파랑
  liquefaction: 0.78, // 보라
  storm_surge: 0.5, // 청록
  tsunami: 0.92, // 자홍
};

/** 심각도(0~1, 클수록 위험)를 짙은 색으로 — 깊을수록/위험할수록 짙다.
 * 최저 등급도 선명하게 보이도록 명도 상한을 낮춰 뒀다(MIN_HAZARD_HEIGHT_M
 * 참고). */
function severityColor(hue: number, severity: number): THREE.Color {
  return new THREE.Color().setHSL(hue, 0.85, 0.55 - severity * 0.3);
}

/** Yellow/Red 존 그대로 — 등급표를 몰라도 색으로 바로 읽힌다. */
function sedimentColor(severity: number): THREE.Color {
  return severity >= 1.0 ? new THREE.Color(0xdc2626) : new THREE.Color(0xeab308);
}

export function hazardPolygonToShapes(polygon: HazardPolygon): ExtrudedShape[] {
  if (polygon.layer === "sediment") {
    const isRed = polygon.severity >= 1.0;
    const color = sedimentColor(polygon.severity);
    return exteriorRings(polygon.geometry).map((ring) => ({
      ring,
      heightM: isRed ? SEDIMENT_RED_HEIGHT_M : SEDIMENT_YELLOW_HEIGHT_M,
      color,
      opacity: isRed ? 0.60 : 0.35,
      pulse: isRed,
    }));
  }
  const heightM = Math.max(MIN_HAZARD_HEIGHT_M, polygon.severity * MAX_HAZARD_HEIGHT_M);
  const color = severityColor(HAZARD_HUE[polygon.layer] ?? 0.6, polygon.severity);
  return exteriorRings(polygon.geometry).map((ring) => ({ ring, heightM, color, opacity: 0.75 }));
}

/** 저층(초록)일수록 낮고 여유롭게, 상업(주황)일수록 높고 빽빽하게 — 1・2=저층,
 * 9・10=근린상업・상업. */
function zoningColor(youtoId: number): THREE.Color {
  if (youtoId <= 2) return new THREE.Color(0x16a34a);
  if (youtoId <= 4) return new THREE.Color(0x65a30d);
  if (youtoId <= 8) return new THREE.Color(0xca8a04);
  if (youtoId <= 10) return new THREE.Color(0xea580c);
  return new THREE.Color(0x78716c); // 준공업・공업
}

export function zoningPolygonToShapes(polygon: ZoningPolygon): ExtrudedShape[] {
  const color = zoningColor(polygon.youto_id);
  return exteriorRings(polygon.geometry).map((ring) => ({
    ring,
    heightM: polygon.height_m,
    color,
    opacity: 0.7,
  }));
}

/** MLIT 원본 Polygon(홍수·토사재해·용도지역)을 3D 압출로 얹는 커스텀 레이어.
 *
 * metricThreeLayer.ts(역 지점 막대)와 달리 임의 다각형을 압출한다 — 좌표는
 * mercator [0,1] 공간에 그대로 두고(별도 원점 이동 없음), 높이만 미터->
 * mercator 환산해서 쓴다.
 */
export class PolygonThreeLayer implements maplibregl.CustomLayerInterface {
  id = "polygon-three-layer";
  type = "custom" as const;
  renderingMode = "3d" as const;

  private map: MapLibreMap | null = null;
  private renderer: THREE.WebGLRenderer | null = null;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.Camera();
  private readonly meshes = new THREE.Group();
  private pulseMeshes: THREE.Mesh[] = [];

  constructor() {
    this.scene.add(this.meshes);
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(0, -1, 1);
    this.scene.add(sun);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    // MetricThreeLayer 와 같은 canvas/gl 위에서 각자 렌더러를 새로 만들면
    // 서로의 GL 상태를 덮어써 한쪽이 안 그려진다(실사용에서 확인) — 공유한다.
    this.renderer = getSharedRenderer(map.getCanvas(), gl);
  }

  onRemove(): void {
    // 렌더러는 공유 자원이다 — 다른 레이어가 아직 쓰는 중일 수 있어 여기서
    // dispose 하지 않는다. map 자체가 사라지면 canvas/gl 과 함께 정리된다.
    this.renderer = null;
  }

  setShapes(shapes: ExtrudedShape[]): void {
    this.meshes.clear();
    this.pulseMeshes = [];
    for (const { ring, heightM, color, opacity, pulse } of shapes) {
      if (ring.length < 3) continue;

      const points = ring.map(([lon, lat]) => {
        const mercator = maplibregl.MercatorCoordinate.fromLngLat({ lng: lon, lat }, 0);
        return { x: mercator.x, y: mercator.y, unit: mercator.meterInMercatorCoordinateUnits() };
      });
      const shape = new THREE.Shape(points.map((p) => new THREE.Vector2(p.x, p.y)));
      // 폴리곤 안에서 위도 변화가 작아 vertex 하나의 미터 환산으로 충분하다.
      const depth = heightM * points[0].unit;
      const geometry = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false });
      const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshPhongMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide }),
      );
      this.meshes.add(mesh);
      if (pulse) this.pulseMeshes.push(mesh);
    }
    this.map?.triggerRepaint();
  }

  render(
    _gl: WebGL2RenderingContext,
    options: { defaultProjectionData: { mainMatrix: ArrayLike<number> } },
  ): void {
    if (!this.renderer) return;

    // Red Zone 맥박 애니메이션 — opacity 0.43~0.67 사이를 2초 주기로 진동
    if (this.pulseMeshes.length > 0) {
      const t = performance.now() / 1000;
      for (const mesh of this.pulseMeshes) {
        (mesh.material as THREE.MeshPhongMaterial).opacity = 0.55 + 0.12 * Math.sin(t * Math.PI);
      }
    }

    this.camera.projectionMatrix = new THREE.Matrix4().fromArray(
      Array.from(options.defaultProjectionData.mainMatrix),
    );
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
    if (this.pulseMeshes.length > 0) this.map?.triggerRepaint();
  }
}
