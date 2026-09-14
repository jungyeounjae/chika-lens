"use client";

import * as maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Map as MapLibreMap } from "maplibre-gl";
import { getSharedRenderer } from "@/components/sharedThreeRenderer";

const DOME_COLOR = new THREE.Color(0x38bdf8); // sky-400
const RING_COLOR = new THREE.Color(0x7dd3fc); // sky-300

const PULSE_SPEED = 1.4; // rad/s
const RING_RISE_S = 2.0; // seconds per ring cycle
const RING_COUNT = 3;

/** 추천 역 위에 반투명 3D 돔 + 스캐닝 링 애니메이션을 얹는 커스텀 레이어.
 *
 * - 돔: 반구(SphereGeometry 상반구)를 sky-blue 반투명으로 올린다. opacity를 사인 파로
 *   진동시켜 "호흡" 효과를 낸다.
 * - 링: RING_COUNT 개의 토러스가 지면(z=0)에서 돔 꼭대기까지 위로 솟으며 사라지는
 *   루프를 반복한다 — 스캐닝 레이더 느낌.
 *
 * MetricThreeLayer·PolygonThreeLayer와 같은 canvas/gl 위에서 동작하므로
 * getSharedRenderer 로 렌더러를 공유한다(GL 상태 충돌 방지).
 */
export class DomeScanLayer implements maplibregl.CustomLayerInterface {
  id = "dome-scan-layer";
  type = "custom" as const;
  renderingMode = "3d" as const;

  private map: MapLibreMap | null = null;
  private renderer: THREE.WebGLRenderer | null = null;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.Camera();
  private readonly group = new THREE.Group();

  private dome: THREE.Mesh | null = null;
  private rings: THREE.Mesh[] = [];

  private cx = 0;
  private cy = 0;
  private unit = 0;
  private radiusM = 500;
  private active = false;

  constructor() {
    this.scene.add(this.group);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 0.5);
    sun.position.set(0, -1, 1);
    this.scene.add(sun);
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    this.renderer = getSharedRenderer(map.getCanvas(), gl);
  }

  onRemove(): void {
    this.renderer = null;
  }

  setStation(lat: number, lon: number, radiusM = 500): void {
    const m = maplibregl.MercatorCoordinate.fromLngLat({ lng: lon, lat }, 0);
    this.cx = m.x;
    this.cy = m.y;
    this.unit = m.meterInMercatorCoordinateUnits();
    this.radiusM = radiusM;
    this.active = true;
    this._rebuild();
    this.map?.triggerRepaint();
  }

  clear(): void {
    this.active = false;
    this.group.clear();
    this.dome = null;
    this.rings = [];
    this.map?.triggerRepaint();
  }

  private _rebuild(): void {
    this.group.clear();
    this.rings = [];

    const r = this.radiusM * this.unit;

    // 돔 — 상반구(thetaStart=0, thetaLength=π/2).
    // Three.js 기본은 Y-up이므로 rotateX(-π/2) 로 Z-up(지도 기준 위쪽)으로 돌린다.
    const domeGeo = new THREE.SphereGeometry(r, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2);
    domeGeo.rotateX(-Math.PI / 2);
    this.dome = new THREE.Mesh(
      domeGeo,
      new THREE.MeshPhongMaterial({
        color: DOME_COLOR,
        transparent: true,
        opacity: 0.12,
        side: THREE.FrontSide,
        depthWrite: false,
      }),
    );
    this.dome.position.set(this.cx, this.cy, 0);
    this.group.add(this.dome);

    // 돔 바닥 테두리 링 — 돔과 지면의 경계를 시각적으로 강조한다.
    const edgeGeo = new THREE.TorusGeometry(r, r * 0.008, 6, 128);
    const edge = new THREE.Mesh(
      edgeGeo,
      new THREE.MeshBasicMaterial({ color: DOME_COLOR, transparent: true, opacity: 0.5, depthWrite: false }),
    );
    edge.position.set(this.cx, this.cy, 0);
    this.group.add(edge);

    // 스캐닝 링 — RING_COUNT 개를 위상(phase) 균등 간격으로 나눠 스태거한다.
    // TorusGeometry 기본은 XY 평면에 눕혀져 있어(= 지도 평면과 일치) 별도 회전 불필요.
    for (let i = 0; i < RING_COUNT; i++) {
      const ringGeo = new THREE.TorusGeometry(r, r * 0.016, 8, 128);
      const ring = new THREE.Mesh(
        ringGeo,
        new THREE.MeshBasicMaterial({
          color: RING_COLOR,
          transparent: true,
          opacity: 0,
          depthWrite: false,
        }),
      );
      ring.position.set(this.cx, this.cy, 0);
      this.group.add(ring);
      this.rings.push(ring);
    }
  }

  render(
    _gl: WebGL2RenderingContext,
    options: { defaultProjectionData: { mainMatrix: ArrayLike<number> } },
  ): void {
    if (!this.renderer || !this.active) return;

    const t = performance.now() / 1000;

    // 돔 호흡 애니메이션
    if (this.dome) {
      (this.dome.material as THREE.MeshPhongMaterial).opacity =
        0.10 + 0.06 * Math.sin(t * PULSE_SPEED);
    }

    // 링 스캔 애니메이션: 각 링은 지면(z=0)→돔 꼭대기(z=r) 를 phase 0→1 로 이동,
    // opacity 는 1→0 으로 페이드아웃한다.
    const maxH = this.radiusM * this.unit;
    for (let i = 0; i < this.rings.length; i++) {
      const phase = (t / RING_RISE_S + i / RING_COUNT) % 1;
      this.rings[i].position.z = phase * maxH;
      (this.rings[i].material as THREE.MeshBasicMaterial).opacity = (1 - phase) * 0.9;
    }

    this.camera.projectionMatrix = new THREE.Matrix4().fromArray(
      Array.from(options.defaultProjectionData.mainMatrix),
    );
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
    this.map?.triggerRepaint(); // 애니메이션 지속
  }
}
