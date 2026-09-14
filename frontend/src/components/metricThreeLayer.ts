"use client";

import * as maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Map as MapLibreMap } from "maplibre-gl";
import { getSharedRenderer } from "@/components/sharedThreeRenderer";
import type { DistributionPoint } from "@/lib/types";

const MAX_BAR_HEIGHT_M = 600;
const BAR_RADIUS_M = 120;
const PARTICLE_COUNT_PER_POINT = 30;
const PARTICLE_SPREAD_M = 250;
const PARTICLE_BOB_AMPLITUDE_M = 60;
const PARTICLE_BOB_SPEED = 1.4;

/** 막대가 무엇을 강조하는지 — 방향에 따라 "높다"의 의미가 반대다.
 *
 * - `highIsBad`: percentile 낮음(위험)일수록 막대가 높고 빨갛다. 재해위험 등
 *   `NEGATIVE_METRICS`/`HAZARD_LAYER_METRICS`(percentile 이 이미 "높을수록
 *   안전"으로 뒤집혀 있는 지표)에 쓴다.
 * - `highIsIntense`: percentile 높음(수치가 큼)일수록 막대가 높고 빨갛다.
 *   `daily_ridership`처럼 좋고 나쁨이 없는 `DIRECTIONLESS_METRICS`에 쓴다 —
 *   "많다/적다"만 보여주지 "좋다/나쁘다"로 읽히면 안 된다.
 */
export type BarDirection = "highIsBad" | "highIsIntense";

export interface MetricBarConfig {
  direction: BarDirection;
  /** 이 백분위보다 위험한(highIsBad 기준) 점에만 파티클을 얹는다.
   * 생략하면 파티클을 안 띄운다 — 모든 지표에 파티클이 어울리진 않는다. */
  particleThresholdPercentile?: number;
}

/** direction 에 따라 "강조 축"으로 뒤집은 백분위. 항상 0(약함)~100(강함). */
function emphasis(point: DistributionPoint, direction: BarDirection): number {
  const p = Math.max(0, Math.min(100, point.percentile));
  return direction === "highIsBad" ? 100 - p : p;
}

function barHeightM(point: DistributionPoint, direction: BarDirection): number {
  if (point.is_missing) return 0;
  return (emphasis(point, direction) / 100) * MAX_BAR_HEIGHT_M;
}

/** 강할수록 빨강, 약할수록 초록 — AreaMap.tsx 의 2D 색점과 같은 색상표를
 * "강조 축" 기준으로 공유한다. */
function colorForEmphasis(strength: number): THREE.Color {
  const hue = ((100 - strength) * 1.2) / 360;
  return new THREE.Color().setHSL(hue, 0.65, 0.45);
}

/** 지표 하나를 지도 위 3D 막대(+선택적 파티클)로 얹는 커스텀 레이어.
 *
 * maplibre 의 2D 색점 마커(AreaMap.tsx)는 그대로 두고 이 레이어를 덧붙인다 —
 * 팝업·클릭 같은 기존 상호작용을 다시 구현할 이유가 없다. 순수 시각 효과다.
 * 재해위험(highIsBad)·유동인구(highIsIntense) 둘 다 이 클래스 하나를 쓴다 —
 * 둘의 차이는 "방향"뿐이라 레이어를 따로 둘 이유가 없다.
 */
export class MetricThreeLayer implements maplibregl.CustomLayerInterface {
  id = "metric-three-layer";
  type = "custom" as const;
  renderingMode = "3d" as const;

  private map: MapLibreMap | null = null;
  private renderer: THREE.WebGLRenderer | null = null;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.Camera();
  private readonly bars = new THREE.Group();
  private readonly boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  private particles: THREE.Points | null = null;
  private particleBaseZ: Float32Array | null = null;
  private particlePhase: Float32Array | null = null;
  private particleAmplitude: Float32Array | null = null;
  private readonly startTime = performance.now();

  constructor() {
    this.scene.add(this.bars);
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(0, -1, 1);
    this.scene.add(sun);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    // PolygonThreeLayer 와 같은 canvas/gl 위에서 각자 렌더러를 새로 만들면
    // 서로의 GL 상태를 덮어써 한쪽이 안 그려진다(실사용에서 확인) — 공유한다.
    this.renderer = getSharedRenderer(map.getCanvas(), gl);
  }

  onRemove(): void {
    // 렌더러는 공유 자원이다 — 다른 레이어가 아직 쓰는 중일 수 있어 여기서
    // dispose 하지 않는다. map 자체가 사라지면 canvas/gl 과 함께 정리된다.
    this.renderer = null;
  }

  /** distribution 결과가 바뀔 때마다 다시 짠다 — 분포 조회 때만 호출돼
   * 빈도가 낮으므로 diff 갱신 없이 매번 새로 만든다. */
  setPoints(points: DistributionPoint[], config: MetricBarConfig): void {
    this.bars.clear();
    const particlePositions: number[] = [];
    const baseZs: number[] = [];
    const phases: number[] = [];
    const amplitudes: number[] = [];

    for (const point of points) {
      const heightM = barHeightM(point, config.direction);
      if (heightM <= 0) continue;

      const strength = emphasis(point, config.direction);
      const base = maplibregl.MercatorCoordinate.fromLngLat(
        { lng: point.lon, lat: point.lat },
        0,
      );
      const meterInMercator = base.meterInMercatorCoordinateUnits();
      const height = heightM * meterInMercator;

      const bar = new THREE.Mesh(
        this.boxGeometry,
        new THREE.MeshPhongMaterial({
          color: colorForEmphasis(strength),
          transparent: true,
          opacity: 0.85,
        }),
      );
      // 메르카토르 좌표계는 z 가 위쪽이다 — 박스 중심을 바닥에서 절반만큼 올린다.
      const width = BAR_RADIUS_M * meterInMercator * 2;
      bar.scale.set(width, width, height);
      bar.position.set(base.x, base.y, base.z + height / 2);
      this.bars.add(bar);

      const threshold = config.particleThresholdPercentile;
      if (threshold === undefined || 100 - strength >= threshold) continue;
      for (let i = 0; i < PARTICLE_COUNT_PER_POINT; i++) {
        const angle = Math.random() * Math.PI * 2;
        const spread = Math.random() * PARTICLE_SPREAD_M * meterInMercator;
        particlePositions.push(
          base.x + Math.cos(angle) * spread,
          base.y + Math.sin(angle) * spread,
          base.z + height,
        );
        baseZs.push(base.z + height);
        phases.push(Math.random() * Math.PI * 2);
        amplitudes.push(PARTICLE_BOB_AMPLITUDE_M * meterInMercator);
      }
    }

    this.rebuildParticles(particlePositions, baseZs, phases, amplitudes);
    this.map?.triggerRepaint();
  }

  private rebuildParticles(
    positions: number[],
    baseZs: number[],
    phases: number[],
    amplitudes: number[],
  ): void {
    if (this.particles) {
      this.scene.remove(this.particles);
      this.particles.geometry.dispose();
      (this.particles.material as THREE.Material).dispose();
      this.particles = null;
    }
    this.particleBaseZ = null;
    this.particlePhase = null;
    this.particleAmplitude = null;
    if (positions.length === 0) return;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    this.particles = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        color: 0xff5544,
        size: 6,
        sizeAttenuation: false,
        transparent: true,
        opacity: 0.85,
      }),
    );
    this.particleBaseZ = new Float32Array(baseZs);
    this.particlePhase = new Float32Array(phases);
    this.particleAmplitude = new Float32Array(amplitudes);
    this.scene.add(this.particles);
  }

  private animateParticles(): void {
    if (!this.particles || !this.particleBaseZ || !this.particlePhase || !this.particleAmplitude) {
      return;
    }
    const elapsedSec = (performance.now() - this.startTime) / 1000;
    const position = this.particles.geometry.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < position.count; i++) {
      const bob = Math.sin(elapsedSec * PARTICLE_BOB_SPEED + this.particlePhase[i]);
      position.setZ(i, this.particleBaseZ[i] + bob * this.particleAmplitude[i]);
    }
    position.needsUpdate = true;
  }

  render(
    _gl: WebGL2RenderingContext,
    options: { defaultProjectionData: { mainMatrix: ArrayLike<number> } },
  ): void {
    if (!this.renderer) return;

    this.animateParticles();
    this.camera.projectionMatrix = new THREE.Matrix4().fromArray(
      Array.from(options.defaultProjectionData.mainMatrix),
    );
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);

    // 파티클이 있으면 계속 다시 그려야 흔들림이 애니메이션으로 보인다.
    if (this.particles) this.map?.triggerRepaint();
  }
}
