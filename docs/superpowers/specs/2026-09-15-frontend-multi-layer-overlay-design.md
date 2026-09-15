# 프런트엔드 다중 3D 레이어 동시 표시 — 설계

## 배경

"자동 출력" 이니셔티브(일반 거주 적합성 질문에 관련 3D 시각화를 자동으로 지도에 띄우는 것)의
첫 번째 선행 작업이다. 백엔드가 한 턴에 `park_polygons`와 `school_facilities`를 같이
호출해도, 현재 프런트는 `polygonView`(hazard/zoning/park 중 하나)와 `facilities`가
서로를 지우는 배타적 단일 상태라 마지막 툴 결과만 화면에 남는다. 이 스펙은 그 상태
구조를 여러 개를 동시에 들고 있을 수 있는 배열로 바꾼다. 백엔드 자동 트리거 프롬프트
규칙과 랜드마크 이름 해석은 각각 별도 후속 스펙이다 — 이 문서의 범위 밖이다.

## 목표

- 한 턴에 여러 3D 툴(`hazard_polygons`/`zoning_massing`/`park_polygons`/`school_facilities`)
  결과가 와도 전부 지도에 동시에 그려진다.
- 기존 단일 3D 뷰 동작(하나만 왔을 때의 카메라 이동, 인포카드, 마커/팝업)은 그대로 유지된다.
- `rank_areas`/`metric_distribution`/`explain_area` 같은 비-3D 모드로 전환하거나 새 사용자
  턴이 시작되면 이전 3D 오버레이는 전부 지워진다.

## 아키텍처

`polygonView: PolygonView | null` + `facilities: SchoolFacilitiesResult | null` 두 상태를
`overlays: Overlay[]` 배열 하나로 통합한다.

```typescript
// frontend/src/lib/types.ts 근처 또는 AreaMap.tsx (기존 PolygonView 선언 자리)
export type Overlay =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult }
  | { kind: "park"; result: ParkPolygonResult }
  | { kind: "facilities"; result: SchoolFacilitiesResult };
```

기존 `PolygonView` 타입(`hazard`/`zoning`/`park` 3종)은 제거하고 `Overlay`로 대체한다
(`facilities` 케이스가 추가된 것 외엔 동일한 구조).

### `page.tsx` — SSE 이벤트 핸들러 (기존: 75-206행)

- `const [polygonView, setPolygonView] = useState<PolygonView | null>(null)`(54행)과
  `const [facilities, setFacilities] = useState<SchoolFacilitiesResult | null>(null)`(56행)을
  `const [overlays, setOverlays] = useState<Overlay[]>([])` 하나로 교체한다.
- 3D 오버레이를 생성하는 4개 분기(134-177행: `hazard_polygons`/`zoning_massing`/
  `park_polygons`/`school_facilities`)는 각각 `setPolygonView(...)`/`setFacilities(...)`
  호출 대신 `setOverlays((prev) => [...prev, { kind: "...", result }])`로 append한다.
  같은 종류(`kind`)가 이미 배열에 있으면 교체한다(같은 턴에 같은 툴이 중복 호출되는
  경우를 대비 — 예: `prev.filter((o) => o.kind !== "park").concat([...])`).
- `setHighlightStation`은 각 분기가 지금처럼 자기 결과의 좌표로 계속 설정한다. 이
  스펙은 카메라를 "마지막으로 온 3D 결과" 기준으로 맞춘다 — 여러 결과가 한 턴에
  오면 마지막 이벤트의 좌표가 최종 카메라 위치가 된다(기존에도 여러 이벤트가 순서대로
  오면 `highlightStation`이 매번 마지막 값으로 덮어써졌으므로 동일한 동작이다).
- 3D 오버레이를 생성하는 4개 분기는 서로를 지우지 않지만, 비-3D 모드 3개 분기
  (`ranked.areas`, 84-90행 / `explain_area`, 111-117행 / `metric_distribution`,
  124-130행)는 지금처럼 3D 오버레이를 전부 지운다 — `setPolygonView(null)` +
  `setFacilities(null)` 두 줄을 `setOverlays([])` 한 줄로 교체한다.
- 새 사용자 턴 시작 시 오버레이를 지우는 지점은 없다(기존 코드에도 없다 — 이전 턴의
  3D 오버레이는 새 3D 툴이 오거나 비-3D 모드로 바뀔 때만 지워졌다). 이 동작을 그대로
  유지한다: 새 턴에서 3D 툴이 전혀 안 오면 이전 오버레이가 화면에 남는다(기존
  `polygonView`/`facilities`와 동일한 성질).

### `AreaMap.tsx` — props와 렌더 (기존: 85-374행)

- `polygonView?: PolygonView | null`(104행)과 `facilities?: SchoolFacilitiesResult | null`
  (107행) props를 `overlays?: Overlay[]`로 교체한다(기본값 `[]`).
- 174-260행의 `if (polygonView) {...return;} ... if (facilities) {...return;}` 상호 배타
  분기를 하나의 블록으로 합친다:
  - `overlays.length > 0`이면 진입한다. 진입 안 하면(빈 배열) 기존처럼
    `polygonLayer.current?.setShapes([])`, `facilityLayer.current?.setFacilities([])`를
    호출해 지운다(기존 218행, 261행 로직 유지).
  - polygon 계열(`hazard`/`zoning`/`park`) 오버레이들을 `flatMap`으로 모아 하나의
    `shapes` 배열을 만들어 `polygonLayer.current?.setShapes(shapes)` 한 번만 호출한다:
    ```typescript
    const shapes = overlays.flatMap((o) =>
      o.kind === "hazard"
        ? o.result.polygons.flatMap(hazardPolygonToShapes)
        : o.kind === "zoning"
          ? o.result.polygons.flatMap(zoningPolygonToShapes)
          : o.kind === "park"
            ? o.result.polygons.flatMap(parkPolygonToShapes)
            : [],
    );
    ```
  - `facilities` 오버레이들을 `flatMap`으로 모아 `facilityLayer.current?.setFacilities(...)`
    한 번만 호출한다:
    ```typescript
    const allFacilities = overlays
      .filter((o) => o.kind === "facilities")
      .flatMap((o) => o.result.facilities);
    facilityLayer.current?.setFacilities(allFacilities);
    ```
  - 마커/팝업(hazard/zoning/park의 중심점 핀, facilities의 이름 라벨+팝업)도
    `overlays`를 순회하며 각 항목마다 기존 로직(192-199행의 폴리곤 중심 핀, 230-248행의
    facility 라벨)을 그대로 적용한다 — 오버레이 개수만큼 반복.
  - 카메라(`cameraForBounds`+`easeTo`)는 **마지막 오버레이의 좌표/반경**으로 한 번만
    호출한다(`overlays[overlays.length - 1]`) — 여러 개를 한 번에 fit하는 bounds 통합은
    이번 범위에 넣지 않는다(아래 "다루지 않는 것" 참조).
- `useEffect` 의존성 배열(374행)의 `polygonView, facilities`를 `overlays`로 교체한다.

### 인포카드 (`page.tsx`, 기존 222-244행)

- 현재 `{facilities && (...)}`와 `{polygonView && (...)}` 두 개의 독립 블록을,
  `overlays.map((overlay) => (...))`로 교체해 오버레이마다 하나씩(같은 스타일의) 카드를
  렌더링한다. 각 카드 내용(라벨 문구, zoning 전용 주석, attribution)은 기존 조건문
  내용을 그대로 옮긴다 — `facilities` kind는 "학교/보육시설 3D (N건)" 카드, `hazard`/
  `zoning`/`park` kind는 기존 `polygonView.kind` 3분기 라벨 카드.
- 여러 카드가 동시에 쌓일 때의 레이아웃(세로로 쌓기, `absolute bottom-3 left-3` 겹침
  방지)은 구현 시 `flex flex-col gap-2`로 감싸는 정도의 조정이 필요하다 — 상세 CSS는
  구현 단계에서 결정한다.
- 245행 `{!polygonView && distribution && (...)}`의 조건은 `{overlays.length === 0 && distribution && (...)}`로 교체한다.

## 다루지 않는 것 (범위 밖)

- 여러 오버레이의 bounds를 합쳐 한 번에 fit하는 카메라 통합 — 마지막 오버레이 기준
  단일 fit으로 충분하다고 보고 이번 스펙에서 제외한다. 필요해지면 후속 개선으로 다룬다.
- 같은 좌표에 여러 폴리곤 레이어가 겹칠 때의 z-fighting/시각적 우선순위 조정.
- 백엔드가 한 턴에 여러 3D 툴을 실제로 호출하도록 만드는 프롬프트 규칙(다음 서브
  프로젝트).
- 랜드마크 이름 → 좌표 해석(그 다음 서브 프로젝트).

## 테스트

- 프런트 서버 기동 후 브라우저로 직접 확인: 백엔드가 한 턴에 `park_polygons`와
  `school_facilities`를 순서대로 스트리밍한다고 가정한 목(mock) 시나리오, 또는 실제
  챗봇에 "신주쿠교엔 공원이랑 주변 학교 3D로 보여줘" 같은 질문으로 두 툴이 실제로
  호출되는지 확인 후 두 레이어가 동시에 보이는지 검증.
- 기존 단일 오버레이 케이스(hazard만, zoning만, park만, facilities만)가 회귀 없이
  그대로 동작하는지 확인 — 카메라 이동, 인포카드 문구, 마커 팝업 텍스트.
- `metric_distribution`/`rank_areas`/`explain_area` 호출 시 이전 3D 오버레이가 전부
  지워지는지 확인.
