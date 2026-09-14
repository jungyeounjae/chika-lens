# OSM 공원 Polygon 3D 시각화 — 설계

**목표:** "이 동네 공원 있어?", "히카리가오카 근처 녹지 보여줘" 같은 질문에
챗봇이 실제 공원 구역 경계(Polygon)를 3D로 보여줄 수 있게 한다.
`hazard_polygons`/`zoning_massing`과 같은 요청 단위 실시간 조회 패턴이다.

**배경:** 사용자가 제안한 "신축 물건 주변 생활 인프라 3D 시각화"(공원·학교·
대형상업시설) 중 학교/보육시설은 이미 구현했다(`school_facilities`,
2026-09-14). 공원·상점·학교 건물 폴리곤 3개를 순서대로 하기로 했고, 공원이
첫 순서다. MLIT `不動産情報ライブラリ` API를 실제 카탈로그(4장 공개 API
일람, 2026-09-14 확인)에서 확인한 결과 **공원 데이터셋이 아예 없다** —
가장 가까운 `XKT019 자연공원지역`은 국립공원 등 광역 보호구역이지 동네
공원이 아니다. 그래서 새 데이터 소스(OpenStreetMap, Overpass API)가
필요하다 — 실측(2026-09-14, 히카리가오카 반경 1km)으로 `leisure=park`
Polygon 39건, 대부분 실명 확인됨을 확인했다.

## 기존 자산 재사용

- `domain/model/polygon.py`: `HazardPolygon`/`ZoningPolygon`이 이미 있는
  파일 — `ParkPolygon`을 같은 파일에 추가한다.
- `domain/repository.py`: `HazardPolygonSource`/`ZoningPolygonSource`와
  같은 모양의 `ParkPolygonSource` Protocol을 추가한다(`polygons_near(lat,
  lon, radius_m) -> Sequence[ParkPolygon]`).
- `interface/agent/actions.py`의 `act_hazard_polygons`(617번째 줄 근처)가
  반경 클램프 + 에러 dict 반환의 정확한 선례다. `MLIT_ATTRIBUTION` 상수
  (610번째 줄)와 같은 자리에 `OSM_ATTRIBUTION`을 추가한다.
- `frontend/src/components/polygonThreeLayer.ts`의 `hazardPolygonToShapes`/
  `zoningPolygonToShapes`가 GeoJSON Polygon → 3D 압출 메시 변환의 정확한
  선례다 — 공원용 변환 함수 하나만 추가한다.
- `frontend/src/components/AreaMap.tsx`의 `PolygonView` union — 새 state를
  만들지 않고 `{kind: "park", result: ParkPolygonResult}`를 추가한다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과, `mypy --strict` 통과(프로젝트 컨벤션: `uv run mypy src`).
- domain 계층은 `etl`/`infrastructure`를 몰라야 한다 — `ParkPolygon`은
  `domain/model/polygon.py`의 새 값 객체다.
- **호출 예절**: Overpass 공개 서버(`overpass-api.de`)는 실측 결과 3연속
  호출만으로 429(rate limit)를 맞았다 — `SuumoClient`(요청 간격 2초 이상
  강제, 재시도 지수 백오프)와 정확히 같은 패턴을 `OverpassClient`에도
  적용한다. `_MIN_INTERVAL_SECONDS = 2.0`, `_MAX_ATTEMPTS = 3`,
  `_RETRY_STATUS = {429, 500, 502, 503, 504}`(suumo_client.py 그대로).
- **라이선스**: OSM 데이터는 ODbL — 출처 표기 조건으로 자유 이용 가능
  (SUUMO 같은 개인용도 제한이 없다). 응답에 `attribution: "© OpenStreetMap
  contributors"`를 담고, LLM이 답변 끝에 한 줄로 표기한다(MLIT
  attribution과 동일 패턴).
- 좌표는 `lat`/`lon` 직접 받는다(station_id 아님) — `school_facilities`가
  이미 확립한 패턴이다: 역이든 신축 물건이든 좌표만 있으면 동작해야
  한다(`hazard_polygons`/`zoning_massing`은 station_id를 받는 더 오래된
  패턴이지만, 이번 신규 기능은 더 일반화된 최신 패턴을 따른다).
- 반경 상한을 클램프한다 — `_MAX_PARK_RADIUS_M = 1500.0`(school_facilities와
  동일 값, 걸어서 갈 만한 범위 밖은 의미 없음).
- 결측: 공원 이름이 OSM에 없는 경우가 실측에서도 나왔다(예: 이름 없는
  공원 다수) — `ParkPolygon.name: str | None`으로 결측을 명시한다. `None`을
  "이름 없는 공원"으로 지어내지 않는다.

## 컴포넌트

### 1. `domain/model/polygon.py` 수정 — `ParkPolygon` 추가

파일 끝에 추가:

```python
@dataclass(frozen=True)
class ParkPolygon:
    geometry: dict[str, object]
    #: OSM 에 이름이 없는 공원도 있다(실측 확인) — 지어내지 않는다.
    name: str | None
```

### 2. `domain/repository.py` 수정 — `ParkPolygonSource` 포트 추가

파일 끝에 추가(`from chika.domain.model.polygon import` import 블록에
`ParkPolygon`도 추가):

```python
class ParkPolygonSource(Protocol):
    """3D 시각화용 OSM 공원 Polygon 조회 포트. 구현체(infrastructure)가
    Overpass 응답을 이미 GeoJSON으로 변환한 결과만 돌려준다."""

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[ParkPolygon]: ...
```

### 3. `infrastructure/overpass_client.py` (신규) — Overpass API 클라이언트

```python
"""Overpass API(OpenStreetMap) HTTP 클라이언트.

공개 API 라 SUUMO 같은 이용약관 문제는 없다(OSM 데이터는 ODbL — 출처
표기 조건으로 자유 이용). 다만 공개 인스턴스(overpass-api.de)는 실측
결과(2026-09-14) 3연속 호출만으로 429(rate limit)를 맞았다 — SuumoClient
와 같은 호출 간격 강제·재시도 백오프를 그대로 적용한다.

mlit_client.py/suumo_client.py 와 같은 transport 주입 패턴이라 테스트가
실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_MIN_INTERVAL_SECONDS = 2.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume)"

Transport = Callable[[str, bytes], bytes]


class OverpassFetchError(RuntimeError):
    """Overpass 쿼리를 받아오지 못했다."""


def _urllib_transport(url: str, body: bytes) -> bytes:
    request = urllib.request.Request(
        url, data=body, headers={"User-Agent": _USER_AGENT}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw: bytes = response.read()
        return raw


class OverpassClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def query(self, overpass_ql: str) -> str:
        """Overpass QL 쿼리 문자열을 실행하고 원본 JSON 텍스트를 돌려준다."""
        self._throttle()
        body = urllib.parse.urlencode({"data": overpass_ql}).encode("utf-8")
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(_OVERPASS_URL, body)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise OverpassFetchError(f"HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise OverpassFetchError(f"연결 실패: {exc.reason}") from exc
            self.calls_made += 1
            return raw.decode("utf-8", errors="replace")
        raise OverpassFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
```

### 4. `infrastructure/overpass_park_source.py` (신규)

```python
"""`ParkPolygonSource` 포트의 실제 구현 — Overpass(OSM) 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와
같은 구조 — 배치가 아니라 요청 한 건을 위해 Overpass 를 실시간으로
호출한다.
"""

from __future__ import annotations

import json
import math

from chika.domain.model.polygon import ParkPolygon
from chika.etl.overpass_client import OverpassClient


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) — Overpass 가 요구하는 순서 그대로."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


class OverpassParkSource:
    def __init__(self, client: OverpassClient) -> None:
        self._client = client

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[ParkPolygon]:
        south, west, north, east = _bbox(lat, lon, radius_m)
        query = (
            "[out:json][timeout:25];"
            f'way["leisure"="park"]({south},{west},{north},{east});'
            "out geom;"
        )
        raw = self._client.query(query)
        data = json.loads(raw)

        polygons: list[ParkPolygon] = []
        for element in data.get("elements", []):
            geometry = element.get("geometry")
            if not isinstance(geometry, list) or len(geometry) < 3:
                continue
            coordinates = [[point["lon"], point["lat"]] for point in geometry]
            tags = element.get("tags") or {}
            polygons.append(
                ParkPolygon(
                    geometry={"type": "Polygon", "coordinates": [coordinates]},
                    name=tags.get("name"),
                )
            )
        return polygons
```

**주의**: `way["leisure"="park"]` 는 닫힌 way(첫/끝 노드 동일)를 전제한다 —
Overpass의 `out geom`은 way의 노드 순서를 그대로 좌표 배열로 준다. 실측
데이터에서 모든 공원이 닫힌 폴리곤이었다(2026-09-14 확인) — 다각형이 안
닫힌 예외 케이스가 나오면 프런트가 마지막에 첫 점을 자동으로 잇지 않으므로
좌표가 이상하게 보일 수 있다. 이번 범위에서는 별도 검증을 추가하지 않는다
(YAGNI) — 실사용에서 문제가 보이면 후속으로 닫힘 검증을 추가한다.

### 5. `application/usecase/park_polygons.py` (신규)

```python
"""공원 Polygon 실시간 조회 — 3D 시각화 재료. hazard_polygons.py 와 같은 구조.

station_id 가 아니라 좌표를 직접 받는다 — school_facilities.py 와 같은
이유(역이든 신축 물건이든 lat/lon 만 있으면 동작해야 한다).
"""

from __future__ import annotations

from chika.domain.model.polygon import ParkPolygon
from chika.domain.repository import ParkPolygonSource

RADIUS_M = 800.0  # hazard_polygons 의 역세권 반경과 동일


class ParkPolygons:
    def __init__(self, source: ParkPolygonSource) -> None:
        self._source = source

    def execute(self, lat: float, lon: float, radius_m: float = RADIUS_M) -> list[ParkPolygon]:
        return list(self._source.polygons_near(lat, lon, radius_m))
```

### 6. 에이전트 배선

**`interface/agent/state.py`**: `UseCases`에 `park_polygons: ParkPolygons`
필드 추가(`school_facilities` 필드 바로 뒤).

**`interface/agent/actions.py`**: `OSM_ATTRIBUTION` 상수를
`MLIT_ATTRIBUTION` 옆에 추가:

```python
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
_MAX_PARK_RADIUS_M = 1500.0
```

파일 끝에 액션 추가:

```python
def act_park_polygons(
    state: SessionState, lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 하나 주변의 공원 원본 Polygon — 3D 압출 시각화 재료.

    hazard_polygons 와 같은 이유로 요청마다 Overpass 를 실시간 호출한다.
    """
    radius = max(1.0, min(radius_m, _MAX_PARK_RADIUS_M))
    try:
        polygons = state.usecases.park_polygons.execute(lat, lon, radius_m=radius)
    except OverpassFetchError as exc:
        return {"error": "overpass_unavailable", "detail": str(exc)}

    return {
        "lat": lat,
        "lon": lon,
        "radius_m": radius,
        "attribution": OSM_ATTRIBUTION,
        "polygons": [
            {"geometry": p.geometry, "name": p.name} for p in polygons
        ],
    }
```

(`from chika.etl.overpass_client import OverpassFetchError` 를 파일 상단
import 블록에 추가한다.)

**`interface/agent/tools.py`**: `@function_tool`

```python
@function_tool
def park_polygons(
    ctx: RunContextWrapper[SessionState], lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 주변의 공원 원본 구역 경계(Polygon)를 낸다 — 3D 녹지 시각화 재료.

    "공원 있어?", "녹지 가까워?" 같은 질문에 쓴다. `lat`/`lon`은
    `rank_areas`/`search_new_construction`/`school_facilities` 결과에 이미
    있는 좌표를 그대로 넘긴다. 결과 0건은 "이 반경 안에 공원 없음"이지
    오류가 아니다. `name`이 `null`이면 OSM에 이름이 등록 안 된 공원이다 —
    "이름 미상의 공원"이라고 답하되 이름을 지어내지 않는다.
    """
    return actions.act_park_polygons(ctx.context, lat=lat, lon=lon, radius_m=radius_m)
```

**`interface/agent/agents.py`**: import + `AnalysisAgent.tools` 끝에 추가.

**`interface/agent/prompts.py`**: `school_facilities` 안내 문단 뒤에 새
bullet 추가 — 정확한 삽입 지점은 구현 시점에 재확인한다.

**`interface/cli.py`**: `_mlit_client()` 옆에 Overpass 클라이언트는
API 키가 없으므로 그냥 `OverpassClient()`를 직접 생성한다.
`build_demo_session`/`build_real_session` 둘 다에
`park_polygons=ParkPolygons(OverpassParkSource(OverpassClient()))` 추가
(`hazard_polygons=...` 근처).

### 7. 프런트엔드

**`frontend/src/lib/types.ts`**: 추가

```typescript
export type ParkPolygon = {
  geometry: GeoJsonGeometry;
  name: string | null;
};

export type ParkPolygonResult = {
  lat: number;
  lon: number;
  radius_m: number;
  attribution: string;
  polygons: ParkPolygon[];
};
```

**`frontend/src/components/AreaMap.tsx`**: `PolygonView` union에 추가:

```typescript
export type PolygonView =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult }
  | { kind: "park"; result: ParkPolygonResult };
```

실제 코드(2026-09-14 확인, `AreaMap.tsx:173-190`)는 다음 두 지점을 고친다:

1. **shapes 분기** (176-179번째 줄) — 현재 `polygonView.kind === "hazard" ?
   ... : ...` 2지 삼항이다. `kind`로 분기하는 `switch`나 3지 조건으로
   바꾼다: `hazard`→`hazardPolygonToShapes`, `zoning`→
   `zoningPolygonToShapes`, `park`→`parkPolygonToShapes`.
2. **핀 팝업 텍스트** (182·188번째 줄) — `const { lat, lon, name_ja, ward,
   radius_m } = polygonView.result;`는 `hazard`/`zoning` 결과에만 있는
   `name_ja`/`ward`(역 이름·구)를 꺼낸다. `ParkPolygonResult`는 좌표 기준
   조회라 이 필드가 없다 — **`park`일 때는 `name_ja`/`ward` 대신 고정
   문구를 쓴다**: `polygonView.kind === "park" ? "공원 지역" : `${name_ja}
   (${ward})``처럼 팝업 텍스트 자체를 kind별로 분기한다. `lat`/`lon`/
   `radius_m`는 세 kind 모두 공통이니 그대로 쓴다.

**`frontend/src/components/polygonThreeLayer.ts`**: 실제 코드를 직접 확인한
결과(2026-09-14), 이 파일은 `ExtrudedShape` 타입(`{ring, heightM, color,
opacity, pulse?}`)과 `exteriorRings(geometry)`(GeoJSON Polygon/MultiPolygon
에서 외곽 링만 뽑는 헬퍼)를 이미 export 하고 있다. `hazardPolygonToShapes`/
`zoningPolygonToShapes` 옆에 그대로 이 두 가지를 재사용해서 추가한다:

```typescript
const PARK_COLOR = new THREE.Color(0x4ade80); // green-400
const PARK_HEIGHT_M = 2.0;

export function parkPolygonToShapes(polygon: ParkPolygon): ExtrudedShape[] {
  return exteriorRings(polygon.geometry).map((ring) => ({
    ring,
    heightM: PARK_HEIGHT_M,
    color: PARK_COLOR,
    opacity: 0.55,
  }));
}
```

**`frontend/src/app/page.tsx`**: `polygonView` 정보 카드(2026-09-14 확인,
`page.tsx:218-227`)도 `kind === "hazard" ? "재해위험 3D..." : "용도지역
3D..."` 2지 삼항이다 — `park`일 때 `"공원 3D (OSM)"` 같은 라벨을 내도록
3지로 확장한다. `attribution`은 `polygonView.result.attribution`을 그대로
쓰므로(모든 kind 공통 필드) 이 줄은 수정 불필요.

## 에러 처리 / 결측 의미론

- Overpass 호출 실패 → `{"error": "overpass_unavailable", "detail": ...}`.
- 반경 상한 초과 시 조용히 클램프(에러 아님).
- 공원 0건은 정상.
- 공원 이름 결측(`name: null`)은 "이름 없음"이지 "공원 아님"이 아니다 —
  Polygon 자체는 그대로 표시한다.

## 테스트

- `tests/etl/test_overpass_client.py`(신규) — `test_suumo_client.py` 패턴
  (transport 주입, 429 재시도, 호출 간격 강제 확인).
- `tests/infrastructure/test_overpass_park_source.py`(신규) — bbox 계산,
  Overpass 응답 → `ParkPolygon` 변환(이름 있음/없음 둘 다), 짧은
  geometry(2점 이하) 제외.
- `tests/application/test_park_polygons.py`(신규) — `test_hazard_polygons.py`
  패턴, fake source 위임 확인.
- `tests/interface/test_agent_actions.py`에 `act_park_polygons` 테스트 +
  기존 `UseCases(...)` 생성 지점 전부에 필드 추가(구현 시점에 정확한 개수
  재확인 — school_facilities 때 6→7개로 이미 한 번 늘었다).
- `tests/interface/test_agent_wiring.py` 툴셋에 `park_polygons` 추가.
- 수동 검증: 실좌표(히카리가오카)로 `act_park_polygons` 직접 호출해 실제
  공원이 나오는지 확인(Task 5 스타일, Overpass 실 서버 호출 — SUUMO 때처럼
  1회성 저빈도로).

## 이번 범위 밖

- 상점/편의점, 학교 건물 폴리곤 — 각자 별도 스펙(순서상 다음·다다음).
- 프런트엔드 3D 렌더링 통합 테스트 — 백엔드 툴 배선 + 프런트 컴포넌트
  코드까지만, 브라우저 수동 확인은 구현 후 별도로 한다.
- 안 닫힌 Polygon 방어 로직 — 실측에서 안 나왔으므로 YAGNI.
