"use client";

import * as maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Map as MapLibreMap } from "maplibre-gl";
import { getSharedRenderer } from "@/components/sharedThreeRenderer";
import type { SchoolFacility } from "@/lib/types";

const MARKER_HEIGHT_M = 80;
const MARKER_RADIUS_M = 35;

// 유치원·보육시설(따뜻한 색)과 초등·중학교(파랑)를 구분한다 — kind 원문
// (mlit_childcare.py 가 그대로 낸 일본어)을 지어내 번역하지 않고 그대로
// 문자열 매칭만 한다.
const PRESCHOOL_COLOR = 0xff8a3d;
const SCHOOL_COLOR = 0x3d7aff;

/** AreaMap.tsx 의 라벨 마커도 같은 기준으로 색을 맞춘다 — 3D 마커 색과
 * 라벨 테두리 색이 따로 놀면 "이 라벨이 저 마커 것"이라는 연결이 깨진다. */
export function isPreschoolKind(kind: string): boolean {
  return kind.includes("幼稚園") || kind.includes("保育");
}

/** 학교/보육시설 좌표마다 작은 3D 원뿔 마커를 세우는 커스텀 레이어.
 *
 * MetricThreeLayer(지표 막대)와 같은 구조다 — 막대 높이/색이 percentile을
 * 따르는 것과 달리, 여기는 전부 같은 높이고 색만 종별(유치원/보육 vs
 * 학교)로 나뉜다. 파티클·애니메이션 없음 — 정적 마커라 매 프레임 다시
 * 그릴 이유가 없다.
 */
export class FacilityThreeLayer implements maplibregl.CustomLayerInterface {
  id = "facility-three-layer";
  type = "custom" as const;
  renderingMode = "3d" as const;

  private map: MapLibreMap | null = null;
  private renderer: THREE.WebGLRenderer | null = null;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.Camera();
  private readonly markers = new THREE.Group();
  private readonly coneGeometry = new THREE.ConeGeometry(1, 1, 12);

  constructor() {
    this.scene.add(this.markers);
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(0, -1, 1);
    this.scene.add(sun);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    // 다른 커스텀 레이어들과 같은 canvas/gl 위에서 렌더러를 새로 만들면
    // 서로의 GL 상태를 덮어쓴다(sharedThreeRenderer.ts 참고) — 공유한다.
    this.renderer = getSharedRenderer(map.getCanvas(), gl);
  }

  onRemove(): void {
    this.renderer = null;
  }

  /** 조회 결과가 바뀔 때마다 다시 짠다 — 호출 빈도가 낮아 diff 갱신 없이
   * 매번 새로 만든다(MetricThreeLayer.setPoints와 같은 이유). */
  setFacilities(facilities: SchoolFacility[]): void {
    this.markers.clear();

    for (const facility of facilities) {
      const base = maplibregl.MercatorCoordinate.fromLngLat(
        { lng: facility.lon, lat: facility.lat },
        0,
      );
      const meterInMercator = base.meterInMercatorCoordinateUnits();
      const height = MARKER_HEIGHT_M * meterInMercator;
      const radius = MARKER_RADIUS_M * meterInMercator;

      const cone = new THREE.Mesh(
        this.coneGeometry,
        new THREE.MeshPhongMaterial({
          color: isPreschoolKind(facility.kind) ? PRESCHOOL_COLOR : SCHOOL_COLOR,
          transparent: true,
          opacity: 0.9,
        }),
      );
      // 메르카토르 좌표계는 z 가 위쪽이다 — 원뿔을 세우려면 x축으로 90도
      // 돌려야 한다(기본은 y축이 위인 원뿔이다).
      cone.rotation.x = Math.PI / 2;
      cone.scale.set(radius, radius, height);
      cone.position.set(base.x, base.y, base.z + height / 2);
      this.markers.add(cone);
    }

    this.map?.triggerRepaint();
  }

  render(
    _gl: WebGL2RenderingContext,
    options: { defaultProjectionData: { mainMatrix: ArrayLike<number> } },
  ): void {
    if (!this.renderer) return;

    this.camera.projectionMatrix = new THREE.Matrix4().fromArray(
      Array.from(options.defaultProjectionData.mainMatrix),
    );
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
  }
}
