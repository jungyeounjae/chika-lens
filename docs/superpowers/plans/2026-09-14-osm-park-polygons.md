# OSM 공원 Polygon 3D 시각화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 좌표(lat/lon) 하나를 주면 그 주변 공원(OSM `leisure=park`)을 실시간으로 조회해 3D 녹지 시각화 재료(Polygon 좌표 + 이름)를 돌려주는 에이전트 툴을 추가하고, 프런트엔드에서 초록 반투명 3D 블록으로 렌더링한다.

**Architecture:** `hazard_polygons`/`zoning_massing`/`school_facilities`와 같은 4계층 실시간 조회 패턴(domain 포트 → infrastructure Overpass 어댑터 → application usecase → interface 4단 배선)이되, 데이터 소스가 MLIT이 아니라 새 외부 API(Overpass, OpenStreetMap)라는 점이 다르다. `school_facilities`처럼 좌표를 직접 받는다(station_id 아님). 프런트엔드는 기존 `PolygonView`/`polygonThreeLayer.ts` 인프라를 그대로 확장한다(새 상태를 만들지 않는다).

**Tech Stack:** 기존 스택 그대로(Python 3.12, MapLibre + Three.js). 새 외부 서비스 하나 추가: Overpass API(`overpass-api.de`, 공개, 키 불필요, ODbL 라이선스).

**Spec:** `docs/superpowers/specs/2026-09-14-osm-park-polygons-design.md`

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 Python 파일 상단.
- `ruff` lint 통과, `mypy --strict` 통과(프로젝트 컨벤션: `uv run mypy src`). 프런트엔드는 `npm run lint` 통과.
- domain 계층은 `etl`/`infrastructure`를 몰라야 한다 — `ParkPolygon`은 domain 전용 값 객체다.
- **호출 예절**: Overpass 공개 서버는 실측(2026-09-14)에서 3연속 호출만으로 429를 맞았다 — `SuumoClient`와 정확히 같은 스로틀·재시도 패턴(`_MIN_INTERVAL_SECONDS = 2.0`, `_MAX_ATTEMPTS = 3`, `_RETRY_STATUS = {429, 500, 502, 503, 504}`)을 `OverpassClient`에도 적용한다.
- 라이선스: OSM은 ODbL — 응답에 `attribution: "© OpenStreetMap contributors"`를 포함한다.
- 좌표는 `lat`/`lon` 직접 받는다(station_id 아님) — `school_facilities`와 같은 패턴.
- 반경 상한 `_MAX_PARK_RADIUS_M = 1500.0`으로 클램프한다.
- 결측: 공원 이름이 OSM에 없는 경우가 실측에서 확인됐다 — `ParkPolygon.name: str | None`으로 결측을 명시하고 지어내지 않는다.
- `UseCases`(`interface/agent/state.py`)는 `frozen=True` dataclass라 필드 하나를 추가하면 **모든 생성 지점**을 고쳐야 한다 — 2026-09-14 기준 정확히 7곳: `backend/src/chika/interface/cli.py:67`(`build_demo_session`), `cli.py:127`(`build_real_session`), `backend/tests/interface/test_agent_actions.py:132`, `:154`, `:1040`, `:1147`, `:1280`. **구현 시작 전에 반드시 `grep -n "UseCases(" backend/src/chika/interface/cli.py backend/tests/interface/test_agent_actions.py`로 재확인** — 이 숫자는 school_facilities 작업 때도 5→6→7로 계속 늘었다.

## 사전 조사 결과 (재사용할 기존 코드)

- `etl/suumo_client.py`: `SuumoClient`가 transport 주입·스로틀·재시도의 정확한 선례다. `OverpassClient`는 GET 대신 POST(쿼리 바디)라는 점만 다르다.
- `infrastructure/mlit_hazard_source.py`: 실시간 조회 → 도메인 타입 변환의 선례.
- `application/usecase/hazard_polygons.py`: usecase가 포트에 위임만 하는 선례(단, `school_facilities.py`처럼 station_id가 아니라 좌표를 직접 받는다).
- `interface/agent/actions.py:610`의 `MLIT_ATTRIBUTION`, `:617`의 `act_hazard_polygons`(반경 클램프 + 에러 dict 반환)가 정확한 선례.
- `interface/agent/prompts.py:484-489`의 `school_facilities` 안내 문단 — 490번째 줄(`"신축", "분양"` 문단) 바로 앞에 새 문단을 끼워 넣는다.
- `frontend/src/components/polygonThreeLayer.ts`: `ExtrudedShape` 타입, `exteriorRings()`, `hazardPolygonToShapes()`/`zoningPolygonToShapes()`(59-94번째 줄)가 정확한 선례.
- `frontend/src/components/AreaMap.tsx:173-190`: `polygonView` 렌더링 분기 — `park` kind 추가 시 `name_ja`/`ward`가 없다는 점을 반드시 반영한다(아래 Task 6 참고).
- `frontend/src/app/page.tsx:218-227`: `polygonView` 정보 카드 — 여기도 3지 분기로 확장한다.

---

## Task 1: 도메인 값 객체 + 리포지토리 포트

**Files:**
- Modify: `backend/src/chika/domain/model/polygon.py`
- Modify: `backend/src/chika/domain/repository.py`
- Test: `backend/tests/domain/model/test_park_polygon.py`

**Interfaces:**
- Produces: `ParkPolygon(geometry: dict[str, object], name: str | None)`(frozen dataclass), `ParkPolygonSource` Protocol(`polygons_near(lat: float, lon: float, radius_m: float) -> Sequence[ParkPolygon]`). Task 3(infrastructure)·Task 4(usecase)·Task 5(agent)가 이 타입들을 그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/domain/model/test_park_polygon.py
"""ParkPolygon 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.polygon import ParkPolygon


def test_a_park_polygon_can_be_constructed_with_a_name() -> None:
    polygon = ParkPolygon(
        geometry={"type": "Polygon", "coordinates": [[[139.6, 35.76], [139.61, 35.76], [139.61, 35.77], [139.6, 35.77], [139.6, 35.76]]]},
        name="北原公園",
    )
    assert polygon.name == "北原公園"
    assert polygon.geometry["type"] == "Polygon"


def test_a_park_polygon_can_have_a_missing_name() -> None:
    """OSM 에 이름이 없는 공원도 실측에서 나왔다 — None 허용, 지어내지 않는다."""
    polygon = ParkPolygon(geometry={"type": "Polygon", "coordinates": []}, name=None)
    assert polygon.name is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_park_polygon.py -v`
Expected: FAIL — `ImportError: cannot import name 'ParkPolygon' from 'chika.domain.model.polygon'`

- [ ] **Step 3: `domain/model/polygon.py`에 `ParkPolygon` 추가**

파일 끝에 추가(기존 `HazardPolygon`/`ZoningPolygon` 뒤):

```python
@dataclass(frozen=True)
class ParkPolygon:
    geometry: dict[str, object]
    #: OSM 에 이름이 없는 공원도 있다(실측 확인, 2026-09-14). 지어내지 않는다.
    name: str | None
```

- [ ] **Step 4: `domain/repository.py`에 `ParkPolygonSource` 포트 추가**

`backend/src/chika/domain/repository.py`의 `from chika.domain.model.polygon
import HazardPolygon, ZoningPolygon` 같은 import 줄에 `ParkPolygon`도
추가한다. 파일 끝에 Protocol 추가:

```python
class ParkPolygonSource(Protocol):
    """3D 시각화용 OSM 공원 Polygon 조회 포트. 구현체(infrastructure)가
    Overpass 응답을 이미 GeoJSON으로 변환한 결과만 돌려준다."""

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[ParkPolygon]: ...
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_park_polygon.py -v`
Expected: PASS (2 passed)

Run also: `cd backend && uv run pytest -q` (전체 스위트 확인 — `ParkPolygonSource`를 아직 아무도 구현/소비하지 않으므로 새 실패는 없어야 한다.)

- [ ] **Step 6: 커밋**

```bash
git add backend/src/chika/domain/model/polygon.py backend/src/chika/domain/repository.py backend/tests/domain/model/test_park_polygon.py
git commit -m "feat(domain): 공원 Polygon 값 객체 + 리포지토리 포트 추가"
```

---

## Task 2: Overpass API 클라이언트

**Files:**
- Create: `backend/src/chika/etl/overpass_client.py`
- Test: `backend/tests/etl/test_overpass_client.py`

**Interfaces:**
- Produces: `OverpassClient(transport=..., sleep=...)`, `.query(overpass_ql: str) -> str`(원본 JSON 텍스트), `OverpassFetchError`. Task 3이 이 클래스를 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_overpass_client.py
"""OverpassClient — 스로틀, 재시도. suumo_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.overpass_client import OverpassClient, OverpassFetchError


def test_query_returns_decoded_body() -> None:
    def transport(url: str, body: bytes) -> bytes:
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    assert client.query("[out:json];way(1,2,3,4);out geom;") == '{"elements": []}'


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str, body: bytes) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    assert client.query("q") == '{"elements": []}'
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str, body: bytes) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(OverpassFetchError, match="400"):
        client.query("q")
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_two_seconds_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str, body: bytes) -> bytes:
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.query("q")
    assert sleeps and sleeps[0] > 1.9
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_overpass_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.overpass_client'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/overpass_client.py
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

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/etl/test_overpass_client.py -v` — 4 passed 기대.
Run: `cd backend && uv run ruff check src/chika/etl/overpass_client.py tests/etl/test_overpass_client.py && uv run mypy src/chika/etl/overpass_client.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/overpass_client.py backend/tests/etl/test_overpass_client.py
git commit -m "feat(etl): Overpass API 클라이언트 추가(스로틀+재시도)"
```

---

## Task 3: Overpass 공원 조회 인프라

**Files:**
- Create: `backend/src/chika/infrastructure/overpass_park_source.py`
- Test: `backend/tests/infrastructure/test_overpass_park_source.py`

**Interfaces:**
- Consumes: `ParkPolygon`(Task 1), `OverpassClient`(Task 2).
- Produces: `OverpassParkSource(client: OverpassClient)`, `.polygons_near(lat: float, lon: float, radius_m: float) -> list[ParkPolygon]`. Task 5가 이 클래스를 `cli.py`에서 인스턴스화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/infrastructure/test_overpass_park_source.py
"""OverpassParkSource — Overpass 응답 파싱 + GeoJSON 변환."""

from __future__ import annotations

import json

from chika.etl.overpass_client import OverpassClient
from chika.infrastructure.overpass_park_source import OverpassParkSource

QUERY_LAT, QUERY_LON = 35.760, 139.609


def _client_returning(elements: list[dict[str, object]]) -> OverpassClient:
    def transport(url: str, body: bytes) -> bytes:
        return json.dumps({"elements": elements}).encode()

    return OverpassClient(transport=transport, sleep=lambda _: None)


def _way(name: str | None, points: list[tuple[float, float]]) -> dict[str, object]:
    """points 는 (lat, lon) 순서 — Overpass `out geom` 응답과 동일."""
    element: dict[str, object] = {
        "type": "way",
        "geometry": [{"lat": lat, "lon": lon} for lat, lon in points],
    }
    if name is not None:
        element["tags"] = {"name": name}
    return element


_SQUARE = [(35.759, 139.608), (35.759, 139.610), (35.761, 139.610), (35.761, 139.608), (35.759, 139.608)]


def test_a_named_park_is_parsed_with_its_polygon() -> None:
    client = _client_returning([_way("北原公園", _SQUARE)])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(polygons) == 1
    assert polygons[0].name == "北原公園"
    assert polygons[0].geometry["type"] == "Polygon"
    coordinates = polygons[0].geometry["coordinates"]
    assert coordinates[0][0] == [139.608, 35.759]  # [lon, lat] 순서로 변환됐는지


def test_a_park_without_a_name_stays_none() -> None:
    """OSM 에 이름이 없는 공원도 있다 — 지어내지 않는다."""
    client = _client_returning([_way(None, _SQUARE)])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert polygons[0].name is None


def test_a_way_with_too_few_points_is_skipped() -> None:
    client = _client_returning([_way("점두개", [(35.759, 139.608), (35.760, 139.609)])])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert polygons == []


def test_no_elements_returns_an_empty_list() -> None:
    client = _client_returning([])
    source = OverpassParkSource(client)

    assert source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0) == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/infrastructure/test_overpass_park_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.infrastructure.overpass_park_source'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/infrastructure/overpass_park_source.py
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

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/infrastructure/test_overpass_park_source.py -v` — 4 passed 기대.
Run: `cd backend && uv run ruff check src/chika/infrastructure/overpass_park_source.py tests/infrastructure/test_overpass_park_source.py && uv run mypy src/chika/infrastructure/overpass_park_source.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/infrastructure/overpass_park_source.py backend/tests/infrastructure/test_overpass_park_source.py
git commit -m "feat(infra): 공원 Polygon Overpass 실시간 조회 인프라 추가"
```

---

## Task 4: 검색 유스케이스

**Files:**
- Create: `backend/src/chika/application/usecase/park_polygons.py`
- Test: `backend/tests/application/test_park_polygons.py`

**Interfaces:**
- Consumes: `ParkPolygonSource`(Task 1 포트), `ParkPolygon`(Task 1).
- Produces: `ParkPolygons(source: ParkPolygonSource)`, `.execute(lat: float, lon: float, radius_m: float = 800.0) -> list[ParkPolygon]`. Task 5가 이 클래스를 `UseCases`에 넣고 `actions.py`에서 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/application/test_park_polygons.py
"""ParkPolygons 유스케이스 — 포트(ParkPolygonSource)에 위임할 뿐임을 확인한다."""

from __future__ import annotations

from chika.application.usecase.park_polygons import ParkPolygons
from chika.domain.model.polygon import ParkPolygon


class _StubSource:
    def __init__(self, polygons: list[ParkPolygon]) -> None:
        self._polygons = polygons
        self.calls: list[tuple[float, float, float]] = []

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[ParkPolygon]:
        self.calls.append((lat, lon, radius_m))
        return self._polygons


def test_execute_forwards_coordinates_and_radius_to_the_source() -> None:
    source = _StubSource([])
    usecase = ParkPolygons(source)

    usecase.execute(35.76, 139.61, radius_m=900.0)

    assert source.calls == [(35.76, 139.61, 900.0)]


def test_execute_uses_800m_as_the_default_radius() -> None:
    source = _StubSource([])
    usecase = ParkPolygons(source)

    usecase.execute(35.76, 139.61)

    assert source.calls == [(35.76, 139.61, 800.0)]


def test_execute_returns_the_sources_polygons() -> None:
    polygon = ParkPolygon(geometry={"type": "Polygon", "coordinates": []}, name="北原公園")
    usecase = ParkPolygons(_StubSource([polygon]))

    result = usecase.execute(35.76, 139.61)

    assert result == [polygon]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/application/test_park_polygons.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.park_polygons'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/application/usecase/park_polygons.py
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

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/application/test_park_polygons.py -v` — 3 passed 기대.
Run: `cd backend && uv run ruff check src/chika/application/usecase/park_polygons.py tests/application/test_park_polygons.py && uv run mypy src/chika/application/usecase/park_polygons.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/application/usecase/park_polygons.py backend/tests/application/test_park_polygons.py
git commit -m "feat(application): 공원 Polygon 실시간 조회 유스케이스 추가"
```

---

## Task 5: 에이전트 툴 배선 (state/actions/tools/agents/prompts/cli)

**Files:**
- Modify: `backend/src/chika/interface/agent/state.py`
- Modify: `backend/src/chika/interface/agent/actions.py`
- Modify: `backend/src/chika/interface/agent/tools.py`
- Modify: `backend/src/chika/interface/agent/agents.py`
- Modify: `backend/src/chika/interface/agent/prompts.py`
- Modify: `backend/src/chika/interface/cli.py`
- Modify: `backend/tests/interface/test_agent_actions.py`
- Modify: `backend/tests/interface/test_agent_wiring.py`

**Interfaces:**
- Consumes: `ParkPolygons`(Task 4), `OverpassParkSource`(Task 3), `OverpassClient`(Task 2), `ParkPolygon`(Task 1).
- Produces: `act_park_polygons`(actions.py) → `park_polygons`(tools.py, `@function_tool`) → `AnalysisAgent`에 등록.

- [ ] **Step 1: `state.py` 수정**

`backend/src/chika/interface/agent/state.py`의 import 블록에 추가:

```python
from chika.application.usecase.park_polygons import ParkPolygons
```

`UseCases`의 `school_facilities` 필드 바로 뒤에 추가:

```python
    #: 공원 3D 시각화용 — 배치가 아니라 요청 단위 실시간 Overpass(OSM) 호출이다
    #: (park_polygons.py 참고). 좌표 기반이라 역이든 신축 물건이든 쓴다.
    park_polygons: ParkPolygons
```

- [ ] **Step 2: `actions.py`에 함수 추가**

파일 상단 import 블록에 추가:

```python
from chika.etl.overpass_client import OverpassFetchError
```

`MLIT_ATTRIBUTION` 상수(610번째 줄 근처) 바로 뒤에 추가:

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
        "polygons": [{"geometry": p.geometry, "name": p.name} for p in polygons],
    }
```

- [ ] **Step 3: `tools.py`에 툴 추가**

파일 맨 끝(`school_facilities` 함수 뒤)에 추가:

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

- [ ] **Step 4: `agents.py`에 등록**

`from chika.interface.agent.tools import (...)` 블록에 `park_polygons`를
알파벳 순서로 추가하고, `AnalysisAgent`의 `tools=[...]` 리스트 끝에도
추가한다:

```python
from chika.interface.agent.tools import (
    compare_areas,
    explain_area,
    explain_new_construction,
    hazard_polygons,
    lookup_new_construction,
    lookup_station,
    metric_distribution,
    metric_extremes,
    park_polygons,
    rank_areas,
    school_facilities,
    search_new_construction,
    set_criteria,
    ward_price_ranking,
    zoning_massing,
)


def build_agents() -> Agent[SessionState]:
    """진입 에이전트(IntakeAgent)를 반환한다. state는 Runner.run(context=...)로 넘긴다."""
    analysis: Agent[SessionState] = Agent(
        name="AnalysisAgent",
        instructions=ANALYSIS_INSTRUCTIONS,
        tools=[
            rank_areas,
            lookup_station,
            explain_area,
            compare_areas,
            metric_distribution,
            ward_price_ranking,
            metric_extremes,
            hazard_polygons,
            zoning_massing,
            search_new_construction,
            lookup_new_construction,
            explain_new_construction,
            school_facilities,
            park_polygons,
        ],
    )
    ...
```

(`...` 이하 `intake`/`return` 블록은 그대로 둔다.)

- [ ] **Step 5: `prompts.py`에 안내 문단 추가**

`ANALYSIS_INSTRUCTIONS` 안에서 `school_facilities` 안내 문단(현재 484-489
번째 줄)이 끝나고 `- **"신축", "분양", "모델하우스" 관련 질문은
search_new_construction ...` 문단(현재 490번째 줄)이 시작되기 **직전**에
다음 문단을 새 bullet로 끼워 넣는다. 정확한 줄 번호는 구현 시점에
`grep -n "school_facilities\." backend/src/chika/interface/agent/prompts.py`
로 재확인한다:

```
- **"공원 있어?", "녹지 가까워?" 같은 질문은 park_polygons.** `lat`/`lon`은
  방금 조회한 역이나 신축 물건의 좌표를 그대로 쓴다. 결과 0건은 "이 반경
  안에 공원 없음"이지 오류가 아니다. `name`이 `null`이면 OSM에 이름이
  등록 안 된 공원이다 — "이름 미상의 공원"이라고 답하되 이름을 지어내지
  않는다. 답변 끝에 출처(`attribution`, "© OpenStreetMap contributors")를
  한 줄로 밝힌다.
```

- [ ] **Step 6: `cli.py` 수정**

파일 상단 import에 추가:

```python
from chika.application.usecase.park_polygons import ParkPolygons
from chika.etl.overpass_client import OverpassClient
from chika.infrastructure.overpass_park_source import OverpassParkSource
```

`build_demo_session`의 `UseCases(...)` 생성부에서, 기존
`school_facilities=SchoolFacilities(MlitSchoolFacilitySource(client))` 바로
뒤에 추가(Overpass 는 API 키가 없으므로 `OverpassClient()`를 인자 없이
만든다):

```python
            park_polygons=ParkPolygons(OverpassParkSource(OverpassClient())),
```

`build_real_session`도 같은 위치(`school_facilities=...` 바로 뒤)에 동일하게
추가한다.

- [ ] **Step 7: 기존 테스트 5곳에 `park_polygons` 필드 추가**

`backend/tests/interface/test_agent_actions.py`에서 `UseCases(` 생성이
5곳에 있다(2026-09-14 기준 line 132 `_deterministic_state`, line 154
`state` fixture, line 1040 `_state_with_sources`, line 1147
`_state_with_new_construction`, line 1280 `_state_with_school_source`) —
**각각의 `school_facilities=...` 줄 바로 뒤에** 다음 한 줄을 추가한다:

```python
            park_polygons=ParkPolygons(_FakeParkPolygonSource()),
```

이를 위해 파일 상단에 페이크 소스와 import를 추가한다. import 블록에:

```python
from chika.application.usecase.park_polygons import ParkPolygons
from chika.domain.model.polygon import ParkPolygon
from chika.etl.overpass_client import OverpassFetchError
```

(`OverpassFetchError`는 Step 8의 `_RaisingParkPolygonSource`가 바로
쓴다 — 여기서 미리 추가해 둔다.)

`_FakeSchoolFacilitySource` 클래스 뒤에 페이크 소스를 추가한다:

```python
class _FakeParkPolygonSource:
    """`ParkPolygonSource` 포트의 테스트 더블. 실제 Overpass 호출이 없다."""

    def polygons_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[ParkPolygon]:
        return []
```

- [ ] **Step 8: 새 액션 테스트 추가**

같은 파일(`test_agent_actions.py`) 맨 끝에 추가:

```python
# --- park_polygons ---


class _FakeParkPolygonSourceWith:
    def __init__(self, polygons: list[ParkPolygon]) -> None:
        self._polygons = polygons

    def polygons_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[ParkPolygon]:
        return self._polygons


class _RaisingParkPolygonSource:
    """Overpass 서버 장애 시나리오 — `overpass_unavailable` 오류 처리를 검증한다."""

    def polygons_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[ParkPolygon]:
        raise OverpassFetchError("HTTP 503")


def _state_with_park_source(source) -> SessionState:  # noqa: ANN001
    stations = [_station("a")]
    areas = FakeAreaMetricsRepository(stations, [_raw("a")])
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository({}), FakePriceRepository({})),
            explain=ExplainArea(areas, FakePriceRepository({})),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
            hazard_polygons=HazardPolygons(areas, _FakeHazardPolygonSource()),
            zoning_massing=ZoningMassing(areas, _FakeZoningPolygonSource()),
            new_construction=NewConstructionSearch(_FakeNewConstructionRepo([])),
            school_facilities=SchoolFacilities(_FakeSchoolFacilitySource()),
            park_polygons=ParkPolygons(source),
        )
    )


def test_park_polygons_returns_polygons_and_attribution() -> None:
    polygon = ParkPolygon(
        geometry={"type": "Polygon", "coordinates": [[[139.6, 35.76]]]}, name="北原公園"
    )
    session = _state_with_park_source(_FakeParkPolygonSourceWith([polygon]))

    result = act_park_polygons(session, lat=35.76, lon=139.61)

    assert result["polygons"] == [{"geometry": polygon.geometry, "name": "北原公園"}]
    assert result["attribution"] == "© OpenStreetMap contributors"


def test_park_polygons_returns_an_empty_list_when_none_are_nearby() -> None:
    session = _state_with_park_source(_FakeParkPolygonSourceWith([]))

    result = act_park_polygons(session, lat=35.76, lon=139.61)

    assert result["polygons"] == []


def test_park_polygons_clamps_the_radius_to_the_maximum() -> None:
    class _RecordingSource:
        def __init__(self) -> None:
            self.calls: list[tuple[float, float, float]] = []

        def polygons_near(
            self, lat: float, lon: float, radius_m: float
        ) -> list[ParkPolygon]:
            self.calls.append((lat, lon, radius_m))
            return []

    source = _RecordingSource()
    session = _state_with_park_source(source)

    act_park_polygons(session, lat=35.76, lon=139.61, radius_m=999_999.0)

    assert source.calls == [(35.76, 139.61, 1500.0)]


def test_park_polygons_reports_overpass_unavailable_on_error() -> None:
    session = _state_with_park_source(_RaisingParkPolygonSource())

    result = act_park_polygons(session, lat=35.76, lon=139.61)

    assert result == {"error": "overpass_unavailable", "detail": "HTTP 503"}
```

같은 파일 상단 import 블록에 `act_park_polygons`도 추가한다
(`from chika.interface.agent.actions import (...)` 블록, 알파벳 순서).

- [ ] **Step 9: `test_agent_wiring.py`의 정확 툴셋 단언 갱신**

`test_analysis_agent_exposes_the_analysis_tools`의 `assert set(...)` 블록
끝에 `"park_polygons"`를 추가한다:

```python
        "school_facilities",
        "park_polygons",
    }
```

- [ ] **Step 10: 전체 스위트 + ruff/mypy 확인**

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run mypy src
```

전부 통과해야 한다. 기존 다른 툴 테스트가 하나도 깨지지 않아야 한다 —
`UseCases` 필드 추가로 인한 5곳의 누락이 없는지 이 실행이 확인해 준다.

- [ ] **Step 11: 커밋**

```bash
git add backend/src/chika/interface/agent/state.py backend/src/chika/interface/agent/actions.py backend/src/chika/interface/agent/tools.py backend/src/chika/interface/agent/agents.py backend/src/chika/interface/agent/prompts.py backend/src/chika/interface/cli.py backend/tests/interface/test_agent_actions.py backend/tests/interface/test_agent_wiring.py
git commit -m "feat(agent): 공원 Polygon 실시간 조회 툴을 AnalysisAgent에 배선"
```

---

## Task 6: 프런트엔드 3D 렌더링

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/polygonThreeLayer.ts`
- Modify: `frontend/src/components/AreaMap.tsx`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Consumes: 백엔드 `act_park_polygons` 페이로드 모양(`{lat, lon, radius_m, attribution, polygons: [{geometry, name}]}`, Task 5).
- Produces: `ParkPolygon`/`ParkPolygonResult` 타입, `parkPolygonToShapes()`, `PolygonView`의 `park` kind. 프런트엔드는 자동 테스트가 없다(코드베이스 기존 컨벤션) — `npm run lint` + Task 7의 수동 브라우저 확인으로 검증한다.

- [ ] **Step 1: `frontend/src/lib/types.ts`에 타입 추가**

`ZoningMassingResult` 타입 뒤에 추가:

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

- [ ] **Step 2: `frontend/src/components/polygonThreeLayer.ts`에 변환 함수 추가**

파일 상단 import에 `ParkPolygon` 추가:

```typescript
import type { GeoJsonGeometry, HazardPolygon, ParkPolygon, ZoningPolygon } from "@/lib/types";
```

`zoningPolygonToShapes` 함수(86-94번째 줄) 뒤에 추가:

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

- [ ] **Step 3: `frontend/src/components/AreaMap.tsx` 수정**

Import 블록에서 `polygonThreeLayer`에서 가져오는 것에 `parkPolygonToShapes`
추가, `@/lib/types`에서 가져오는 것에 `ParkPolygonResult` 추가:

```typescript
import {
  PolygonThreeLayer,
  hazardPolygonToShapes,
  parkPolygonToShapes,
  zoningPolygonToShapes,
} from "@/components/polygonThreeLayer";
```

```typescript
import type {
  DistributionPoint,
  HazardPolygonResult,
  MapPin,
  NearbyStation,
  ParkPolygonResult,
  SchoolFacilitiesResult,
  ZoningMassingResult,
} from "@/lib/types";
```

`PolygonView` union(24-26번째 줄)에 `park` 추가:

```typescript
export type PolygonView =
  | { kind: "hazard"; result: HazardPolygonResult }
  | { kind: "zoning"; result: ZoningMassingResult }
  | { kind: "park"; result: ParkPolygonResult };
```

렌더링 분기(현재 173-190번째 줄, 정확한 줄 번호는 구현 시점에
`grep -n "if (polygonView)" frontend/src/components/AreaMap.tsx`로
재확인)를 아래처럼 고친다 — **shapes 분기를 3지로, 핀 팝업 텍스트를
kind별로 분기**한다:

```typescript
    if (polygonView) {
      metricLayer.current?.setPoints([], barConfigFor(undefined));
      facilityLayer.current?.setFacilities([]);
      const shapes =
        polygonView.kind === "hazard"
          ? polygonView.result.polygons.flatMap(hazardPolygonToShapes)
          : polygonView.kind === "zoning"
            ? polygonView.result.polygons.flatMap(zoningPolygonToShapes)
            : polygonView.result.polygons.flatMap(parkPolygonToShapes);
      polygonLayer.current?.setShapes(shapes);

      const { lat, lon, radius_m } = polygonView.result;
      const popupText =
        polygonView.kind === "park"
          ? "공원 지역"
          : `${polygonView.result.name_ja} (${polygonView.result.ward})`;
      const pin = document.createElement("div");
      pin.className =
        "h-4 w-4 rounded-full border-2 border-white bg-rose-600 shadow-lg";
      const marker = new maplibregl.Marker({ element: pin })
        .setLngLat([lon, lat])
        .setPopup(new maplibregl.Popup({ offset: 10 }).setText(popupText))
        .addTo(instance);
      markers.current.push(marker);
```

(이하 카메라 이동 코드는 그대로 둔다 — `radius_m`을 그대로 쓴다.)

**주의**: `polygonView.result.name_ja`/`polygonView.result.ward`는
`hazard`/`zoning` kind에서만 타입에 존재한다. TypeScript는 `polygonView.kind
=== "park"` 분기 밖에서 이 필드들에 접근하는 걸 union narrowing으로
허용하지 않을 수 있다 — 컴파일 에러가 나면 `popupText` 계산을 각 kind별
`if`/`else if`/`else` 블록으로 완전히 분리하거나(narrowing이 되도록),
`polygonView.result`를 각 분기 안에서 별도로 구조분해한다. 어느 쪽이든
동작은 동일하다(park→"공원 지역", 나머지→"이름 (구)"). 구현 시점에
`npm run lint`/`npm run build`로 타입 에러 여부를 반드시 확인한다.

`facilities` 관련 effect의 마지막(현재 220번째 줄 근처)에 있는
`polygonLayer.current?.setShapes([]);` 는 그대로 둔다 — `facilities` 분기가
`polygonView` 분기 다음에 실행될 때 이전 폴리곤을 지우는 용도로 이미 쓰이고
있다.

- [ ] **Step 4: `frontend/src/app/page.tsx` 수정**

Import 블록의 `@/lib/types`에서 가져오는 타입에 `ParkPolygonResult` 추가:

```typescript
import type {
  ExplainedArea,
  HazardPolygonResult,
  MapPin,
  MetricDistribution,
  NearbyStation,
  ParkPolygonResult,
  RankedArea,
  SchoolFacilitiesResult,
  ZoningMassingResult,
} from "@/lib/types";
```

`event.tool === "zoning_massing"` 분기(현재 144-154번째 줄 근처, 정확한
줄 번호는 구현 시점에 `grep -n 'event.tool === "zoning_massing"'
frontend/src/app/page.tsx`로 재확인) 뒤, `event.tool === "school_facilities"`
분기 앞 또는 뒤 아무 곳에 추가(순서 무관, 각 분기가 서로 독립적으로
`setFacilities`/`setPolygonView`/`setDistribution`을 상호 초기화하는
기존 패턴을 그대로 따른다):

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

그리고 이미 있는 다른 분기들(`ranked.areas`, `explain_area`,
`metric_distribution`, `hazard_polygons`, `zoning_massing`,
`school_facilities`)에도 **`setPolygonView(null)`을 호출하는 자리마다**
`park_polygons` 결과가 새로 뜨는 걸 막기 위한 추가 초기화는 필요 없다 —
`setPolygonView(...)` 로 다른 kind를 세팅하면 이전 `park` 뷰는 자동으로
덮어써진다(기존 hazard/zoning 상호 관계와 동일). 다만 **`park_polygons`
분기 자체는 `setFacilities(null)`을 호출**해야 한다(위 코드에 이미 포함).

`polygonView` 정보 카드(현재 218-227번째 줄, 정확한 위치는 구현 시점에
`grep -n "polygonView && ("` 로 재확인)의 라벨 삼항을 3지로 확장한다:

```typescript
            <p className="font-medium">
              {polygonView.kind === "hazard"
                ? "재해위험 3D (원본 구역)"
                : polygonView.kind === "zoning"
                  ? "용도지역 3D (원본 구역)"
                  : "공원 3D (OSM)"}
            </p>
```

- [ ] **Step 5: lint 확인**

Run: `cd frontend && npm run lint`
Expected: 기존에 있던 1건의 무관한 경고(`import/no-anonymous-default-export`,
`eslint.config.mjs`) 외에 새 에러 없음.

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/lib/types.ts frontend/src/components/polygonThreeLayer.ts frontend/src/components/AreaMap.tsx frontend/src/app/page.tsx
git commit -m "feat(frontend): 공원 Polygon 3D 렌더링(초록 반투명 블록) 추가"
```

---

## Task 7: 실제 실행으로 수동 검증

- [ ] **Step 1: 백엔드 — 실좌표로 Overpass 조회 확인(외부 네트워크 1회, 저빈도)**

```bash
cd backend
uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_park_polygons

state = build_real_session()
result = act_park_polygons(state, lat=35.760, lon=139.609, radius_m=800.0)
print(f'조회 결과 {len(result[\"polygons\"])}건')
for p in result['polygons'][:10]:
    print(f'  {p[\"name\"]}')
"
```

Expected: 공원이 여러 건 나온다(2026-09-14 실측 기준 800m 반경이면 최소
10건 이상 기대). 이름이 있는 것도, `None`(즉 파이썬에서 `None` 출력)인
것도 섞여 있을 수 있다.

- [ ] **Step 2: 반경 상한 클램프 확인**

```bash
cd backend
uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_park_polygons

state = build_real_session()
result = act_park_polygons(state, lat=35.760, lon=139.609, radius_m=99_999.0)
print(f'요청 반경 99999 -> 실제 사용된 반경: {result[\"radius_m\"]}')
assert result['radius_m'] == 1500.0
print('클램프 정상')
"
```

Expected: `실제 사용된 반경: 1500.0`, `클램프 정상` 출력.

- [ ] **Step 3: 프런트엔드 — 브라우저에서 실제 렌더링 확인**

백엔드/프런트엔드 개발 서버를 둘 다 최신 코드로 재기동한 뒤(이미 떠 있는
프로세스가 이번 변경 전 코드로 떠 있을 수 있다 — 반드시 재시작한다),
브라우저에서 챗봇에 "히카리가오카역 근처 공원 3D로 보여줘" 같은 질문을
입력한다.

Expected:
- 채팅 텍스트가 공원 이름을 구체적으로 나열하고, 답변 끝에
  "출처: © OpenStreetMap contributors" 또는 동등한 한 줄 표기가 있다.
- 지도에 초록 반투명 3D 블록이 여러 개 뜬다(공원 구역 경계 모양).
- 좌측 하단 정보 카드에 "공원 3D (OSM)" 라벨이 보인다.
- 브라우저 콘솔에 새로 생긴 에러가 없다(기존에 있던 stale-chunk 계열
  경고는 무관하니 무시해도 된다).

---

## Self-Review 체크리스트

- **스펙 커버리지**: 스펙의 컴포넌트 7개(domain 값 객체+포트, Overpass
  클라이언트, infrastructure 어댑터, application usecase, 에이전트 4단
  배선, 프런트엔드 3곳 수정, 테스트)를 Task 1~6이 각각 구현하고, Task 7이
  수동 검증한다. 에러 처리(`overpass_unavailable`, 반경 클램프, 0건=정상,
  이름 결측)는 Task 3·5·6에서 모두 구현·테스트된다.
- **플레이스홀더 스캔**: 모든 코드 블록이 실행 가능한 완성 코드다. Task 6의
  TypeScript union narrowing 관련 주의사항은 "구현 시점에 lint/build로
  확인"이라고 명시했는데, 이는 TypeScript 컴파일러 버전에 따라 narrowing
  동작이 달라질 수 있는 실제 불확실성이지 게으름이 아니다 — 구체적인 대안
  두 가지(if/else 분리, 각 분기 내 재구조분해)를 코드 수준으로 제시했다.
- **타입 일관성**: `ParkPolygon`(Task 1 정의: `geometry, name`)이 Task 3
  (`OverpassParkSource.polygons_near` 반환값 구성)·Task 4
  (`ParkPolygons.execute` 반환 타입)·Task 5(`act_park_polygons`의 payload
  dict 키: `geometry`, `name`)·Task 6(프런트 `ParkPolygon` 타입)에서 필드명이
  전부 일치한다. `ParkPolygonSource`(Task 1 Protocol: `polygons_near(lat,
  lon, radius_m)`)를 Task 3의 구현체와 Task 5의 페이크 더블 모두 정확히
  같은 시그니처로 구현한다. `UseCases`에 `park_polygons` 필드를 추가하면서
  생성 지점 7곳(cli.py 2곳, test_agent_actions.py 5곳)을 전부 짚었다.
- **아키텍처 경계**: domain은 etl을 모른다(`ParkPolygon`을 domain에 새로
  정의). infrastructure만 Overpass 구체 의존을 알고, application은 포트
  (Protocol)만 안다 — 기존 `hazard_polygons`/`school_facilities` 배선과
  동일한 패턴. `OverpassClient`는 `etl/` 아래 두되 infrastructure가
  가져다 쓴다 — `mlit_client.py`가 `mlit_hazard_source.py`에 쓰이는 것과
  동일한 기존 선례를 그대로 따른다.
- **호출 예절**: `OverpassClient`가 `SuumoClient`와 동일한 스로틀·재시도
  로직을 갖는지 Task 2의 테스트 4개(정상 응답, 429 재시도, 재시도 안 하는
  4xx, 최소 2초 간격)가 확인한다.
- **프런트엔드 기존 코드와의 통합**: Task 6에서 기존 `AreaMap.tsx:173-190`/
  `page.tsx:218-227`가 `hazard`/`zoning` 2지 분기라는 것과, `park` 결과에는
  `name_ja`/`ward`가 없다는 스펙의 발견을 그대로 반영해 3지 분기 + kind별
  팝업 텍스트 분기로 명시했다 — 스펙 자체 리뷰에서 잡은 문제라 플랜에서도
  놓치지 않았다.
