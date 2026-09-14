"use client";

import * as THREE from "three";

/** 커스텀 레이어 2개(MetricThreeLayer, PolygonThreeLayer)가 같은 canvas/gl
 * 컨텍스트 위에서 각자 `new THREE.WebGLRenderer(...)`를 만들면 서로의 GL
 * 상태(뷰포트·바인딩 등)를 덮어써 한쪽이 안 그려지거나 간헐적으로 깨진다
 * (실사용에서 확인 — 재해위험 3D가 어떤 세션에서는 평면으로만 보였다).
 * 그래서 gl 컨텍스트당 렌더러 하나만 만들어 공유한다. */
const renderers = new WeakMap<WebGL2RenderingContext, THREE.WebGLRenderer>();

export function getSharedRenderer(
  canvas: HTMLCanvasElement,
  gl: WebGL2RenderingContext,
): THREE.WebGLRenderer {
  let renderer = renderers.get(gl);
  if (!renderer) {
    renderer = new THREE.WebGLRenderer({ canvas, context: gl, antialias: true });
    renderer.autoClear = false;
    renderers.set(gl, renderer);
  }
  return renderer;
}
