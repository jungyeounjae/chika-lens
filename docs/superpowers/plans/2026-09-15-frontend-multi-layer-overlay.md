# 프런트엔드 다중 3D 레이어 동시 표시 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `AreaMap`/`page.tsx`의 배타적 단일 3D 상태(`polygonView`/`facilities`)를 하나의
`Overlay[]` 배열로 통합해, 한 턴에 여러 3D 툴(hazard/zoning/park/facilities) 결과가 와도
전부 동시에 지도에 그려지도록 한다.

**Architecture:** `Overlay` 판별 유니온 타입(`AreaMap.tsx`에 정의)을 `page.tsx`가 상태로
들고, SSE 이벤트의 4개 3D 툴 분기가 `setOverlays((prev) => [...])`로 append한다.
`AreaMap.tsx`는 `overlays: Overlay[]` prop을 받아 폴리곤/시설을 flatMap으로 합쳐 각각
한 번씩 레이어에 넘기고, 카메라는 마지막 오버레이 기준으로 맞춘다. 인포카드는
`overlays.map(...)`으로 오버레이마다 하나씩 렌더한다.

**Tech Stack:** Next.js(App Router) + React 19 + TypeScript, MapLibre GL JS, Three.js
(기존 `polygonThreeLayer.ts`/`facilityThreeLayer.ts` 그대로 재사용, 신규 레이어 없음).

**Spec:** [docs/superpowers/specs/2026-09-15-frontend-multi-layer-overlay-design.md](../specs/2026-09-15-frontend-multi-layer-overlay-design.md)

## Global Constraints

- 기존 단일 오버레이 동작(카메라 이동, 인포카드 문구, 마커/팝업 텍스트)은 회귀 없이 유지한다.
- `rank_areas`/`metric_distribution`/`explain_area` 비-3D 모드로 전환되면 오버레이는 전부
  `[]`로 지운다(스펙 — 새 사용자 턴 자체에서는 지우지 않는다, 기존 동작과 동일).
- 카메라는 여러 오버레이의 bounds를 통합하지 않고 **마지막 오버레이 기준 단일 fit**만
  수행한다(스펙 §"다루지 않는 것").
- 이 저장소에 프런트엔드 자동화 테스트 프레임워크가 없다 — 검증은 `npm run build`
  (타입체크 겸용) + `npm run lint` + 브라우저 수동 확인으로 한다.

---

### Task 1: `Overlay` 타입 도입 + `AreaMap.tsx` 렌더링 통합

**Files:**
- Modify: `frontend/src/components/AreaMap.tsx:8-31` (imports, `PolygonView` 타입 제거 후 `Overlay` 타입 추가)
- Modify: `frontend/src/components/AreaMap.tsx:85-119` (컴포넌트 props)
- Modify: `frontend/src/components/AreaMap.tsx:167-261` (렌더 `useEffect` 본문 — 배타적 분기를 통합 분기로 교체)
- Modify: `frontend/src/components/AreaMap.tsx:374` (`useEffect` 의존성 배열)

**Interfaces:**
- Produces: `export type Overlay = { kind: "hazard"; result: HazardPolygonResult } | { kind: "zoning"; result: ZoningMassingResult } | { kind: "park"; result: ParkPolygonResult } | { kind: "facilities"; result: SchoolFacilitiesResult };` — Task 2가 `page.tsx`에서 이 타입을 import해 상태로 쓴다.
- Produces: `AreaMap` 컴포넌트의 새 prop `overlays?: Overlay[]` (기본값 `[]`) — 기존 `polygonView`/`facilities` prop을 대체한다. Task 2가 이 prop에 값을 넘긴다.
- Consumes: 기존에 이미 있는 `hazardPolygonToShapes`, `zoningPolygonToShapes`, `parkPolygonToShapes`(`polygonThreeLayer.ts`), `isPreschoolKind`(`facilityThreeLayer.ts`) — 변경 없음.

- [ ] **Step 1: 기존 `PolygonView` 타입을 `Overlay`로 교체**

`frontend/src/components/AreaMap.tsx`의 26-31행(현재):

```typescript
/** hazard_polygons/zoning_massing/park_polygons 결과 — 원본 Polygon 3D 뷰.
 * distribution/areas 보다 우선한다(가장 구체적인 "역 하나 딥다이브" 모드). */
export type PolygonView =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult }
  | { kind: "park"; result: ParkPolygonResult };
```

을 다음으로 교체한다:

```typescript
/** hazard_polygons/zoning_massing/park_polygons/school_facilities 결과 —
 * 3D 오버레이 하나. distribution/areas 보다 우선한다(가장 구체적인 "역 하나
 * 딥다이브" 모드). 여러 개가 동시에 배열(overlays)에 들어갈 수 있다(스펙
 * 2026-09-15-frontend-multi-layer-overlay-design.md). */
export type Overlay =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult }
  | { kind: "park"; result: ParkPolygonResult }
  | { kind: "facilities"; result: SchoolFacilitiesResult };
```

(`SchoolFacilitiesResult`는 16-24행의 기존 import 목록에 이미 있다 — import 문은
변경할 필요 없다.)

- [ ] **Step 2: props 시그니처 교체**

91-110행(현재):

```typescript
  polygonView = null,
  facilities = null,
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
  /** school_facilities 결과. polygonView 와 같은 우선순위 — 있으면 다른
   * 모드보다 우선하고, 서로 배타적이다(page.tsx 가 상호 초기화한다). */
  facilities?: SchoolFacilitiesResult | null;
  /** 돔+스캐닝 링 강조 표시할 역 — explain_area·rank_areas·hazard_polygons 등
   * 단일 역에 포커스가 생길 때 설정한다. null 이면 숨긴다. */
  highlightStation?: { lat: number; lon: number; radiusM?: number } | null;
}) {
```

를 다음으로 교체한다:

```typescript
  overlays = [],
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
  /** hazard_polygons/zoning_massing/park_polygons/school_facilities 결과들 —
   * 있으면 다른 모드보다 우선하고, 배열의 모든 항목을 동시에 그린다. */
  overlays?: Overlay[];
  /** 돔+스캐닝 링 강조 표시할 역 — explain_area·rank_areas·hazard_polygons 등
   * 단일 역에 포커스가 생길 때 설정한다. null 이면 숨긴다. */
  highlightStation?: { lat: number; lon: number; radiusM?: number } | null;
}) {
```

- [ ] **Step 3: 렌더 `useEffect` 본문의 배타적 분기를 통합 분기로 교체**

167-261행 전체(`const instance = map.current; ... facilityLayer.current?.setFacilities([]);`
까지 — `distribution` 분기 시작 전)를 다음으로 교체한다:

```typescript
    const instance = map.current;
    if (!instance) return;

    markers.current.forEach((marker) => marker.remove());
    markers.current = [];

    // overlays(3D 뷰)가 있으면 area/distribution 마커보다 우선한다 — 다른 걸 다
    // 지우고 이것만 그린다. 여러 개가 동시에 있으면 폴리곤/시설을 전부 합쳐
    // 그린다(스펙 2026-09-15-frontend-multi-layer-overlay-design.md).
    if (overlays.length > 0) {
      metricLayer.current?.setPoints([], barConfigFor(undefined));

      const shapes = overlays.flatMap((overlay) =>
        overlay.kind === "hazard"
          ? overlay.result.polygons.flatMap(hazardPolygonToShapes)
          : overlay.kind === "zoning"
            ? overlay.result.polygons.flatMap(zoningPolygonToShapes)
            : overlay.kind === "park"
              ? overlay.result.polygons.flatMap(parkPolygonToShapes)
              : [],
      );
      polygonLayer.current?.setShapes(shapes);

      const allFacilities = overlays.flatMap((overlay) =>
        overlay.kind === "facilities" ? overlay.result.facilities : [],
      );
      facilityLayer.current?.setFacilities(allFacilities);

      // 폴리곤 계열(hazard/zoning/park)은 오버레이마다 중심점에 핀 하나씩.
      overlays.forEach((overlay) => {
        if (overlay.kind === "facilities") return;
        const { lat, lon } = overlay.result;
        const popupText =
          overlay.kind === "park"
            ? "공원 지역"
            : `${overlay.result.name_ja} (${overlay.result.ward})`;
        const pin = document.createElement("div");
        pin.className =
          "h-4 w-4 rounded-full border-2 border-white bg-rose-600 shadow-lg";
        const marker = new maplibregl.Marker({ element: pin })
          .setLngLat([lon, lat])
          .setPopup(new maplibregl.Popup({ offset: 10 }).setText(popupText))
          .addTo(instance);
        markers.current.push(marker);
      });

      // facilities 오버레이의 시설마다 이름 라벨 + 클릭 시 상세 팝업.
      // 3D 마커만으론 무엇을 가리키는지 안 보인다(색만으로 유치원/학교 구분이
      // 안 됨) — 다른 핀들과 같은 maplibregl.Marker/Popup 패턴을 쓴다.
      allFacilities.forEach((facility) => {
        const preschool = isPreschoolKind(facility.kind);
        const label = document.createElement("div");
        label.style.cssText =
          `border:1.5px solid ${preschool ? "#ff8a3d" : "#3d7aff"};` +
          "border-radius:9999px;background:rgba(23,23,23,.85);color:white;" +
          "padding:2px 8px;font-size:11px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.4);";
        label.textContent = facility.name || facility.kind;
        const marker = new maplibregl.Marker({ element: label, anchor: "bottom" })
          .setLngLat([facility.lon, facility.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 10 }).setText(
              `${facility.name || facility.kind} (${facility.kind}) · ` +
                `도보 약 ${walkMinutes(facility.distance_m)}분(직선거리 ${Math.round(facility.distance_m)}m)`,
            ),
          )
          .addTo(instance);
        markers.current.push(marker);
      });

      // pitch 를 건 뒤 곧바로 별도의 fitBounds/flyTo 를 부르면, 그 두 번째
      // 호출이 "아직 애니메이션 시작 전(=여전히 pitch 0)"인 transform 을
      // 기준으로 자기 카메라 파라미터를 잡아버려 pitch 가 조용히 원위치로
      // 취소된다(실측) — bounds 를 직접 계산해 pitch 와 함께 **단일 easeTo
      // 호출**로 합친다. 카메라는 마지막 오버레이 기준으로만 맞춘다(여러
      // 오버레이 bounds 통합은 범위 밖 — 스펙 참고).
      const last = overlays[overlays.length - 1];
      const { lat, lon, radius_m } = last.result;
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
    facilityLayer.current?.setFacilities([]);
```

- [ ] **Step 4: `useEffect` 의존성 배열 교체**

374행(현재):
```typescript
  }, [areas, numbered, nearby, distribution, distributionMetric, polygonView, facilities, highlightStation]);
```

를:
```typescript
  }, [areas, numbered, nearby, distribution, distributionMetric, overlays, highlightStation]);
```

- [ ] **Step 5: 타입체크 (page.tsx는 아직 미수정 — 에러 예상)**

Run: `cd frontend && npx tsc --noEmit`
Expected: `src/app/page.tsx`에서 `PolygonView`/`polygonView`/`facilities` 관련 타입 에러
발생 — Task 2에서 해결한다. `AreaMap.tsx` 자체에서 발생하는 에러가 없어야 한다(있으면
이 Step에서 고친다).

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/components/AreaMap.tsx
git commit -m "feat(frontend): AreaMap이 Overlay[] 배열로 다중 3D 레이어를 동시에 그리도록 통합"
```

---

### Task 2: `page.tsx` 상태/이벤트 핸들러/인포카드를 `Overlay[]`로 마이그레이션

**Files:**
- Modify: `frontend/src/app/page.tsx:19` (import)
- Modify: `frontend/src/app/page.tsx:53-56` (state)
- Modify: `frontend/src/app/page.tsx:84-177` (SSE 이벤트 핸들러 7개 분기)
- Modify: `frontend/src/app/page.tsx:212-244` (`AreaMap` 호출 + 인포카드)
- Modify: `frontend/src/app/page.tsx:245` (distribution 카드 조건)

**Interfaces:**
- Consumes: Task 1이 만든 `export type Overlay` (from `@/components/AreaMap`), `AreaMap`의
  `overlays?: Overlay[]` prop.
- Produces: 없음 (이 플랜의 마지막 코드 변경 태스크).

- [ ] **Step 1: import 교체**

19행(현재):
```typescript
import type { PolygonView } from "@/components/AreaMap";
```

를:
```typescript
import type { Overlay } from "@/components/AreaMap";
```

- [ ] **Step 2: state 교체**

53-56행(현재):
```typescript
  // hazard_polygons/zoning_massing 결과 — 원본 MLIT Polygon 3D 뷰.
  const [polygonView, setPolygonView] = useState<PolygonView | null>(null);
  // school_facilities 결과 — 좌표 주변 학교/보육시설 3D 마커.
  const [facilities, setFacilities] = useState<SchoolFacilitiesResult | null>(null);
```

를:
```typescript
  // hazard_polygons/zoning_massing/park_polygons/school_facilities 결과들 —
  // 한 턴에 여러 개가 와도 전부 동시에 그린다(스펙
  // 2026-09-15-frontend-multi-layer-overlay-design.md).
  const [overlays, setOverlays] = useState<Overlay[]>([]);
```

(`SchoolFacilitiesResult` import는 8-18행에 남겨둔다 — 아래 Step 3의 `school_facilities`
분기에서 여전히 `event.result as SchoolFacilitiesResult` 캐스팅에 쓰인다.)

- [ ] **Step 3: SSE 이벤트 핸들러 7개 분기 교체**

**3-1. `ranked.areas` 분기 (84-90행)** — 현재:
```typescript
            if (ranked?.areas) {
              setPins(ranked.areas);
              setNumbered(true);
              setNearby([]);
              setDistribution(null);
              setPolygonView(null);
              setFacilities(null);
```

를:
```typescript
            if (ranked?.areas) {
              setPins(ranked.areas);
              setNumbered(true);
              setNearby([]);
              setDistribution(null);
              setOverlays([]);
```

**3-2. `explain_area` 분기 (111-117행)** — 현재:
```typescript
            if (event.tool === "explain_area" && single?.station_id && typeof single.lat === "number") {
              setPins([single as ExplainedArea]);
              setNumbered(false);
              setNearby(single.nearby ?? []);
              setDistribution(null);
              setPolygonView(null);
              setFacilities(null);
```

를:
```typescript
            if (event.tool === "explain_area" && single?.station_id && typeof single.lat === "number") {
              setPins([single as ExplainedArea]);
              setNumbered(false);
              setNearby(single.nearby ?? []);
              setDistribution(null);
              setOverlays([]);
```

**3-3. `metric_distribution` 분기 (124-130행)** — 현재:
```typescript
            if (event.tool === "metric_distribution" && Array.isArray(dist?.points)) {
              // 분포 모드는 순위/단일 조회 핀과 동시에 뜨면 색의 의미가
              // 헷갈린다 — AreaMap이 distribution 이 있으면 그것만 그린다.
              setDistribution(dist as MetricDistribution);
              setPolygonView(null);
              setFacilities(null);
```

를:
```typescript
            if (event.tool === "metric_distribution" && Array.isArray(dist?.points)) {
              // 분포 모드는 순위/단일 조회 핀과 동시에 뜨면 색의 의미가
              // 헷갈린다 — AreaMap이 distribution 이 있으면 그것만 그린다.
              setDistribution(dist as MetricDistribution);
              setOverlays([]);
```

**3-4. `hazard_polygons` 분기 (134-144행)** — 현재:
```typescript
            if (event.tool === "hazard_polygons" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const hazard = event.result as HazardPolygonResult;
              setDistribution(null);
              setPolygonView({ kind: "hazard", result: hazard });
              setFacilities(null);
              setHighlightStation((prev) =>
                prev?.lat === hazard.lat && prev?.lon === hazard.lon && prev?.radiusM === hazard.radius_m
                  ? prev
                  : { lat: hazard.lat, lon: hazard.lon, radiusM: hazard.radius_m },
              );
            }
```

를:
```typescript
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
```

**3-5. `zoning_massing` 분기 (145-155행)** — 같은 패턴으로 현재:
```typescript
            if (event.tool === "zoning_massing" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const zoning = event.result as ZoningMassingResult;
              setDistribution(null);
              setPolygonView({ kind: "zoning", result: zoning });
              setFacilities(null);
              setHighlightStation((prev) =>
                prev?.lat === zoning.lat && prev?.lon === zoning.lon && prev?.radiusM === zoning.radius_m
                  ? prev
                  : { lat: zoning.lat, lon: zoning.lon, radiusM: zoning.radius_m },
              );
            }
```

를:
```typescript
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
```

**3-6. `park_polygons` 분기 (156-166행)** — 현재:
```typescript
            if (event.tool === "park_polygons" && Array.isArray((event.result as { polygons?: unknown })?.polygons)) {
              const park = event.result as ParkPolygonResult;
              setDistribution(null);
              setPolygonView({ kind: "park", result: park });
              setFacilities(null);
              setHighlightStation((prev) =>
                prev?.lat === park.lat && prev?.lon === park.lon && prev?.radiusM === park.radius_m
                  ? prev
                  : { lat: park.lat, lon: park.lon, radiusM: park.radius_m },
              );
            }
```

를:
```typescript
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
```

**3-7. `school_facilities` 분기 (167-177행)** — 현재:
```typescript
            if (event.tool === "school_facilities" && Array.isArray((event.result as { facilities?: unknown })?.facilities)) {
              const school = event.result as SchoolFacilitiesResult;
              setDistribution(null);
              setPolygonView(null);
              setFacilities(school);
              setHighlightStation((prev) =>
                prev?.lat === school.lat && prev?.lon === school.lon && prev?.radiusM === school.radius_m
                  ? prev
                  : { lat: school.lat, lon: school.lon, radiusM: school.radius_m },
              );
            }
```

를:
```typescript
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
```

- [ ] **Step 4: `AreaMap` 호출부와 인포카드 교체**

212-244행(현재, `<AreaMap` 호출부터 `polygonView` 카드 닫는 `)}`까지):
```typescript
        <AreaMap
          areas={pins}
          numbered={numbered}
          nearby={nearby}
          distribution={distribution?.points}
          distributionMetric={distribution?.metric}
          polygonView={polygonView}
          facilities={facilities}
          highlightStation={highlightStation}
        />
        {facilities && (
          <div className="absolute bottom-3 left-3 rounded-lg border border-neutral-200 bg-white/95 px-3 py-2 text-xs shadow dark:border-neutral-700 dark:bg-neutral-900/95">
            <p className="font-medium">학교/보육시설 3D ({facilities.facilities.length}건)</p>
            <p className="mt-0.5 text-neutral-500">
              주황 = 유치원·보육시설, 파랑 = 초등·중학교. 반경 {Math.round(facilities.radius_m)}m 이내.
            </p>
          </div>
        )}
        {polygonView && (
          <div className="absolute bottom-3 left-3 rounded-lg border border-neutral-200 bg-white/95 px-3 py-2 text-xs shadow dark:border-neutral-700 dark:bg-neutral-900/95">
            <p className="font-medium">
              {polygonView.kind === "hazard"
                ? "재해위험 3D (원본 구역)"
                : polygonView.kind === "zoning"
                  ? "용도지역 3D (원본 구역)"
                  : "공원 3D (OSM)"}
            </p>
            {polygonView.kind === "zoning" && (
              <p className="mt-0.5 text-neutral-500">높이는 실제 건축 높이 제한이 아니라 시각적 근사치입니다.</p>
            )}
            <p className="mt-1 text-[10px] text-neutral-500">{polygonView.result.attribution}</p>
          </div>
        )}
```

를 다음으로 교체한다:
```typescript
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
```

- [ ] **Step 5: distribution 카드 조건 교체**

245행(현재):
```typescript
        {!polygonView && distribution && (
```

를:
```typescript
        {overlays.length === 0 && distribution && (
```

- [ ] **Step 6: 타입체크 + 린트**

Run: `cd frontend && npx tsc --noEmit`
Expected: 에러 없음 (Task 1의 `AreaMap.tsx` 에러도 이제 전부 해소되어 있어야 한다).

Run: `cd frontend && npm run lint`
Expected: 에러 없음.

- [ ] **Step 7: 빌드**

Run: `cd frontend && npm run build`
Expected: 빌드 성공.

- [ ] **Step 8: 커밋**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(frontend): page.tsx가 Overlay[] 상태로 여러 3D 툴 결과를 동시에 유지하도록 변경"
```

---

### Task 3: 브라우저 수동 검증

**Files:** 없음(코드 변경 없음 — 검증만).

**Interfaces:**
- Consumes: Task 1+2가 완성한 `overlays` 파이프라인 전체.

- [ ] **Step 1: 프런트/백엔드 서버 기동**

프런트: `cd frontend && npm run dev` (또는 기존에 쓰던 `preview_start`/dev 서버).
백엔드: 기존 방식대로 FastAPI 서버 기동(`uvicorn` 등, 이 세션에서 이미 쓰던 커맨드 사용).

- [ ] **Step 2: 단일 오버레이 회귀 확인 (4종 모두)**

브라우저에서 순서대로 질문해 각각 기존과 동일하게 동작하는지 확인한다:
- "신주쿠역 재해위험 3D로 보여줘" → hazard 카드 1개, 카메라가 해당 역으로 이동, 폴리곤
  색이 기존과 같음.
- "신주쿠역 용도지역 3D로 보여줘" → zoning 카드 1개(높이 근사치 안내 문구 포함).
- "신주쿠교엔 공원 3D로 보여줘" → park 카드 1개.
- "신주쿠역 근처 학교 3D로 보여줘" → facilities 카드 1개(건수/범례 문구 포함), 시설
  라벨과 팝업이 기존과 동일하게 보임.

각 케이스에서 이전 오버레이 카드가 남아있지 않고 새 오버레이 하나만 보여야 한다(같은
`kind`를 다시 요청했을 때 교체되는지 확인 — Step 3의 필터 로직이 올바른지 여기서
같이 확인된다).

- [ ] **Step 3: 다중 오버레이 확인**

이 코드베이스가 한 턴에 여러 3D 툴을 실제로 호출하는 프롬프트 규칙은 아직 없다(다음
서브 프로젝트 범위) — 그래서 이 스텝은 **브라우저 개발자 도구로 직접 확인**한다:

1. React DevTools 또는 콘솔에서 `page.tsx`의 `send` 콜백 실행 중 `setOverlays`를 두 번
   연달아 호출하는 상황을 재현하기 어려우므로, 대신 아래처럼 연속 두 턴을 보낸다:
   "신주쿠교엔 공원 3D로 보여줘" 실행 후, 응답이 끝나면 바로 "신주쿠역 근처 학교
   3D로 보여줘"를 보낸다.
2. 두 번째 질문의 응답이 렌더된 직후 화면에 park 카드와 facilities 카드가 **동시에**
   보이는지 확인한다(현재 `overlays` 배열은 새 사용자 턴에서 지워지지 않으므로, 서로
   다른 `kind`의 두 오버레이가 append되어 쌓여야 한다 — 이것이 이 플랜이 고치는 핵심
   동작이다).
3. 지도에 공원 폴리곤과 학교 3D 마커가 동시에 렌더되어 있는지 확인한다.
4. 이어서 "신주쿠 근처 순위 알려줘"처럼 `rank_areas`를 트리거하는 질문을 보내 두
   카드가 전부 사라지고 순위 핀만 남는지 확인한다(비-3D 모드 전환 시 초기화 확인).

- [ ] **Step 4: 콘솔 에러 확인**

브라우저 콘솔에 새로 발생한 에러/경고가 없는지 확인한다(특히 `maplibregl.Marker`
중복 생성이나 `undefined` 접근 관련 에러).

- [ ] **Step 5: 결과 보고**

Step 2-4의 결과(통과/실패, 스크린샷 필요시 첨부)를 정리해 보고한다. 실패가 있으면
Task 1/2로 돌아가 수정한다 — 이 태스크 자체는 코드를 고치지 않는다.
