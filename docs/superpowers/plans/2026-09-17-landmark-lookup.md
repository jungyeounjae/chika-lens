# 랜드마크 이름 → 좌표 변환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "신주쿠교엔 근처 살기 좋아?"처럼 역이 아닌 지명(공원·랜드마크·관광지)으로 물어도 좌표를 찾아 가장 가까운 역으로 이어서 기존 분석 전체(explain_area/hazard_polygons/zoning_massing/school_facilities/park_polygons)를 그대로 쓸 수 있게 한다.

**Architecture:** Clean Architecture 4계층 그대로 컴포넌트만 추가한다 — domain에 `LandmarkMatch` 값 객체와 `LandmarkGeocoder` 포트, etl에 Nominatim raw HTTP 클라이언트, infrastructure에 그 포트 구현체, application에 가장 가까운 역을 계산하는 `LookupLandmark` usecase, agent 계층에 새 툴 `lookup_landmark`.

**Tech Stack:** Python 3.12, Nominatim(OpenStreetMap) 검색 API(무료, 키 불필요), `urllib`(표준 라이브러리, 다른 HTTP 클라이언트와 동일), pytest.

**Spec:** [docs/superpowers/specs/2026-09-17-landmark-lookup-design.md](../specs/2026-09-17-landmark-lookup-design.md)

## Global Constraints

- Python `>=3.12,<3.13`, 모든 새 파일 상단에 `from __future__ import annotations`.
- `ruff check .` / `mypy --strict`(`uv run mypy src`) / `pytest` 전부 통과.
- domain 계층은 `infrastructure`/`etl`를 몰라야 한다.
- Nominatim 호출 예절: `_MIN_INTERVAL_SECONDS = 1.0`, `_MAX_ATTEMPTS = 3`, `_RETRY_STATUS = {429, 500, 502, 503, 504}`, User-Agent 필수(다른 클라이언트와 같은 문자열 스타일).
- 검색은 `countrycodes=jp`로 일본 내로만 제한한다.
- 가장 가까운 역까지 2,000m(`FAR_FROM_STATION_M`) 초과 시 `far_from_any_station: true`.
- 후보는 최대 3개(`MAX_MATCHES`)만 반환한다.
- 출처 표기: `attribution: "© OpenStreetMap contributors"`(기존 `OSM_ATTRIBUTION` 상수 재사용).
- 네트워크 실패는 `{"error": "geocoder_unavailable", "detail": str(exc)}`로 반환하고 대화를 죽이지 않는다.

---

### Task 1: Domain — `LandmarkMatch` 값 객체 + `LandmarkGeocoder` 포트

**Files:**
- Create: `backend/src/chika/domain/model/landmark.py`
- Modify: `backend/src/chika/domain/repository.py`
- Test: `backend/tests/domain/model/test_landmark.py`

**Interfaces:**
- Produces: `LandmarkMatch(name: str, lat: float, lon: float)`, `LandmarkGeocoder.search(query: str, limit: int) -> Sequence[LandmarkMatch]` — Task 3(구현체)과 Task 4(usecase)가 이 타입을 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/domain/model/test_landmark.py`:

```python
"""LandmarkMatch 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.landmark import LandmarkMatch


def test_a_landmark_match_can_be_constructed() -> None:
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    assert match.name == "新宿御苑"
    assert match.lat == 35.6851
    assert match.lon == 139.7095
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_landmark.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.landmark'`

- [ ] **Step 3: 최소 구현 작성**

`backend/src/chika/domain/model/landmark.py` 새로 생성:

```python
"""랜드마크 지오코딩 결과 값 객체."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LandmarkMatch:
    name: str
    lat: float
    lon: float
```

`backend/src/chika/domain/repository.py` 수정 — 상단 import 블록에서
`from chika.domain.model.facility import SchoolFacility` 다음 줄에
`from chika.domain.model.landmark import LandmarkMatch`를 추가한다(알파벳순:
`facility` 다음, `metrics` 앞). 파일 맨 끝에 다음을 추가:

```python


class LandmarkGeocoder(Protocol):
    """랜드마크/POI 이름 → 좌표 지오코딩 포트. 구현체(infrastructure)가
    외부 API 호출·재시도를 끝낸 결과만 돌려준다."""

    def search(self, query: str, limit: int) -> Sequence[LandmarkMatch]: ...
```

(`Protocol`과 `Sequence`는 이미 파일 상단에 import돼 있다 — 새로 추가할 필요 없다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_landmark.py -v`
Expected: PASS

- [ ] **Step 5: lint/type check**

Run: `cd backend && uv run ruff check . && uv run mypy src`
Expected: 에러 없음

- [ ] **Step 6: 커밋**

```bash
cd backend
git add src/chika/domain/model/landmark.py src/chika/domain/repository.py tests/domain/model/test_landmark.py
git commit -m "feat(domain): 랜드마크 값 객체 + 지오코더 포트 추가"
```

---

### Task 2: etl — `NominatimClient` raw HTTP 클라이언트

**Files:**
- Create: `backend/src/chika/etl/nominatim_client.py`
- Test: `backend/tests/etl/test_nominatim_client.py`

**Interfaces:**
- Consumes: 없음(표준 라이브러리 `urllib`만 사용).
- Produces: `NominatimClient(transport=..., sleep=...)` with
  `.search(query: str, limit: int) -> str`(raw JSON 텍스트), `NominatimFetchError` —
  Task 3이 이 클라이언트를 감싼다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/etl/test_nominatim_client.py` (전체 내용 —
`tests/etl/test_overpass_client.py`와 같은 구조):

```python
"""NominatimClient — 스로틀, 재시도. overpass_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.nominatim_client import NominatimClient, NominatimFetchError


def test_search_returns_decoded_body() -> None:
    def transport(url: str) -> bytes:
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    assert client.search("新宿御苑", limit=3) == "[]"


def test_search_url_carries_query_limit_and_country_filter() -> None:
    seen_urls: list[str] = []

    def transport(url: str) -> bytes:
        seen_urls.append(url)
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    client.search("新宿御苑", limit=3)

    assert len(seen_urls) == 1
    assert "q=" in seen_urls[0]
    assert "limit=3" in seen_urls[0]
    assert "countrycodes=jp" in seen_urls[0]


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    assert client.search("q", limit=1) == "[]"
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(NominatimFetchError, match="400"):
        client.search("q", limit=1)
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_one_second_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str) -> bytes:
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.search("q", limit=1)
    assert sleeps and sleeps[0] > 0.9
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_nominatim_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.nominatim_client'`

- [ ] **Step 3: 최소 구현 작성**

`backend/src/chika/etl/nominatim_client.py` 새로 생성:

```python
"""Nominatim(OpenStreetMap) 지오코딩 API HTTP 클라이언트.

Nominatim 공식 사용 정책 — 초당 1회 이하, 식별 가능한 User-Agent 필수
(https://operations.osmfoundation.org/policies/nominatim/). overpass_client.py
와 같은 transport 주입 패턴이라 테스트가 실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

_BASE_URL = "https://nominatim.openstreetmap.org/search"
_MIN_INTERVAL_SECONDS = 1.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume)"

Transport = Callable[[str], bytes]


class NominatimFetchError(RuntimeError):
    """Nominatim 검색 요청이 실패했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw: bytes = response.read()
        return raw


class NominatimClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0

    def search(self, query: str, limit: int) -> str:
        """질의 문자열로 검색하고 원본 JSON 텍스트를 돌려준다."""
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "limit": limit, "countrycodes": "jp"}
        )
        url = f"{_BASE_URL}?{params}"
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise NominatimFetchError(f"HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise NominatimFetchError(f"연결 실패: {exc.reason}") from exc
            return raw.decode("utf-8", errors="replace")
        raise NominatimFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_nominatim_client.py -v`
Expected: PASS (5개 테스트)

- [ ] **Step 5: lint/type check**

Run: `cd backend && uv run ruff check . && uv run mypy src`
Expected: 에러 없음

- [ ] **Step 6: 커밋**

```bash
cd backend
git add src/chika/etl/nominatim_client.py tests/etl/test_nominatim_client.py
git commit -m "feat(etl): Nominatim 지오코딩 HTTP 클라이언트 추가"
```

---

### Task 3: infrastructure — `NominatimGeocoder` (포트 구현체)

**Files:**
- Create: `backend/src/chika/infrastructure/nominatim_geocoder.py`
- Test: `backend/tests/infrastructure/test_nominatim_geocoder.py`

**Interfaces:**
- Consumes: `NominatimClient`(Task 2), `LandmarkMatch`(Task 1).
- Produces: `NominatimGeocoder(client: NominatimClient)` implementing
  `LandmarkGeocoder`(`.search(query, limit) -> list[LandmarkMatch]`) —
  Task 5(합성 루트)가 이걸 조립해 넘긴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/infrastructure/test_nominatim_geocoder.py`:

```python
"""NominatimGeocoder — Nominatim 응답 파싱 + LandmarkMatch 변환."""

from __future__ import annotations

import json

import pytest

from chika.etl.nominatim_client import NominatimClient, NominatimFetchError
from chika.infrastructure.nominatim_geocoder import NominatimGeocoder


def _client_returning(elements: list[dict[str, object]]) -> NominatimClient:
    def transport(url: str) -> bytes:
        return json.dumps(elements).encode()

    return NominatimClient(transport=transport, sleep=lambda _: None)


def test_a_named_result_is_parsed_into_a_landmark_match() -> None:
    client = _client_returning(
        [{"name": "新宿御苑", "lat": "35.6851", "lon": "139.7095", "display_name": "新宿御苑, 東京都"}]
    )
    geocoder = NominatimGeocoder(client)

    matches = geocoder.search("신주쿠교엔", limit=3)

    assert len(matches) == 1
    assert matches[0].name == "新宿御苑"
    assert matches[0].lat == 35.6851
    assert matches[0].lon == 139.7095


def test_a_result_without_a_name_falls_back_to_display_name() -> None:
    client = _client_returning(
        [{"lat": "35.68", "lon": "139.70", "display_name": "内藤町, 新宿区, 東京都"}]
    )
    geocoder = NominatimGeocoder(client)

    matches = geocoder.search("q", limit=3)

    assert matches[0].name == "内藤町"


def test_an_empty_array_returns_no_matches() -> None:
    client = _client_returning([])
    geocoder = NominatimGeocoder(client)
    assert geocoder.search("존재하지 않는 곳", limit=3) == []


def test_a_non_json_response_raises_a_fetch_error() -> None:
    def transport(url: str) -> bytes:
        return b"not json"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    geocoder = NominatimGeocoder(client)

    with pytest.raises(NominatimFetchError):
        geocoder.search("q", limit=3)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/infrastructure/test_nominatim_geocoder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.infrastructure.nominatim_geocoder'`

- [ ] **Step 3: 최소 구현 작성**

`backend/src/chika/infrastructure/nominatim_geocoder.py` 새로 생성:

```python
"""`LandmarkGeocoder` 포트의 실제 구현 — Nominatim(OSM) 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. overpass_park_source.py 와
같은 구조 — 배치가 아니라 요청 한 건을 위해 Nominatim 을 실시간으로
호출한다.
"""

from __future__ import annotations

import json

from chika.domain.model.landmark import LandmarkMatch
from chika.etl.nominatim_client import NominatimClient, NominatimFetchError


class NominatimGeocoder:
    def __init__(self, client: NominatimClient) -> None:
        self._client = client

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        raw = self._client.search(query, limit)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NominatimFetchError(
                f"Nominatim 응답이 JSON이 아니다 (길이 {len(raw)}자): {raw[:200]!r}"
            ) from exc
        if not isinstance(data, list):
            raise NominatimFetchError(f"Nominatim 응답이 배열이 아니다: {raw[:200]!r}")

        matches: list[LandmarkMatch] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            lat_raw, lon_raw = item.get("lat"), item.get("lon")
            if lat_raw is None or lon_raw is None:
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                display_name = item.get("display_name")
                name = display_name.split(",")[0] if isinstance(display_name, str) else query
            matches.append(LandmarkMatch(name=name, lat=float(lat_raw), lon=float(lon_raw)))
        return matches
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/infrastructure/test_nominatim_geocoder.py -v`
Expected: PASS (4개 테스트)

- [ ] **Step 5: lint/type check**

Run: `cd backend && uv run ruff check . && uv run mypy src`
Expected: 에러 없음

- [ ] **Step 6: 커밋**

```bash
cd backend
git add src/chika/infrastructure/nominatim_geocoder.py tests/infrastructure/test_nominatim_geocoder.py
git commit -m "feat(infra): Nominatim 지오코딩 포트 구현체 추가"
```

---

### Task 4: application — `LookupLandmark` usecase (가장 가까운 역 계산)

**Files:**
- Create: `backend/src/chika/application/usecase/lookup_landmark.py`
- Test: `backend/tests/application/test_lookup_landmark.py`

**Interfaces:**
- Consumes: `LandmarkGeocoder`(Task 1 포트), `AreaMetricsRepository.stations()`,
  `chika.domain.service.geo.distance_meters(lat1, lon1, lat2, lon2) -> float`(기존).
- Produces: `LookupLandmark(areas, geocoder)` with `.execute(query: str) ->
  list[LandmarkCandidate]`; `LandmarkCandidate(match, nearest_station:
  NearestStation | None, far_from_any_station: bool)`;
  `NearestStation(station: Station, distance_m: float)` — Task 5의
  `act_lookup_landmark`가 이 반환값을 그대로 dict로 펼친다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/application/test_lookup_landmark.py`:

```python
"""LookupLandmark 유스케이스 — 가장 가까운 역 계산 + 거리 상한 플래그."""

from __future__ import annotations

from chika.application.usecase.lookup_landmark import FAR_FROM_STATION_M, LookupLandmark
from chika.domain.model.landmark import LandmarkMatch
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


class _FakeGeocoder:
    def __init__(self, matches: list[LandmarkMatch]) -> None:
        self._matches = matches
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        self.calls.append((query, limit))
        return self._matches


def _station(station_id: str, lat: float, lon: float) -> Station:
    return Station(id=station_id, name_ja=station_id, ward="新宿区", lat=lat, lon=lon, lines=())


def test_finds_the_nearest_station_for_each_match() -> None:
    # 新宿御苑 근처: a는 도보권, b는 (Station의 도쿄 bbox 안에서) 훨씬 멀다.
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository(
        [_station("a", 35.6860, 139.7100), _station("b", 35.80, 139.80)], []
    )
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("신주쿠교엔")

    assert len(candidates) == 1
    assert candidates[0].nearest_station is not None
    assert candidates[0].nearest_station.station.id == "a"


def test_flags_far_from_any_station_beyond_the_cap() -> None:
    # 가장 가까운 역도 2,000m 훨씬 밖에 있도록(Station의 도쿄 bbox 안에서) 좌표를 벌린다.
    match = LandmarkMatch(name="외딴곳", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository([_station("a", 35.80, 139.80)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("외딴곳")

    assert candidates[0].nearest_station is not None
    assert candidates[0].nearest_station.distance_m > FAR_FROM_STATION_M
    assert candidates[0].far_from_any_station is True


def test_does_not_flag_a_station_within_the_cap() -> None:
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository([_station("a", 35.6860, 139.7100)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("신주쿠교엔")

    assert candidates[0].far_from_any_station is False


def test_returns_an_empty_list_when_the_geocoder_finds_nothing() -> None:
    areas = FakeAreaMetricsRepository([_station("a", 35.68, 139.70)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([]))

    assert usecase.execute("존재하지 않는 곳") == []


def test_passes_the_query_and_max_matches_limit_to_the_geocoder() -> None:
    areas = FakeAreaMetricsRepository([_station("a", 35.68, 139.70)], [])
    geocoder = _FakeGeocoder([])
    usecase = LookupLandmark(areas, geocoder)

    usecase.execute("신주쿠교엔")

    assert geocoder.calls == [("신주쿠교엔", 3)]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/application/test_lookup_landmark.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.lookup_landmark'`

- [ ] **Step 3: 최소 구현 작성**

`backend/src/chika/application/usecase/lookup_landmark.py` 새로 생성:

```python
"""랜드마크 이름 → 좌표 → 가장 가까운 역. 3D/좌표 기반 툴 및 station_id
기반 분석 전체(explain_area 등)의 입구를 역이 아닌 지명에도 열어준다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.landmark import LandmarkMatch
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, LandmarkGeocoder
from chika.domain.service.geo import distance_meters

#: 가장 가까운 역도 이보다 멀면 "이 역 데이터가 실제 지점과 거리가 있다"고
#: 경고한다 — 조용히 먼 역 데이터를 그 지점 것처럼 말하는 걸 막는다.
FAR_FROM_STATION_M = 2_000.0

#: 후보가 많아도 LLM 컨텍스트를 채우지 않도록 자른다(lookup_station 의
#: MAX_LOOKUP_MATCHES 보다 작게 잡는다 — 랜드마크는 이름이 훨씬 덜 겹친다).
MAX_MATCHES = 3


@dataclass(frozen=True)
class NearestStation:
    station: Station
    distance_m: float


@dataclass(frozen=True)
class LandmarkCandidate:
    match: LandmarkMatch
    nearest_station: NearestStation | None  # 역 목록이 비어있을 리 없지만 방어적으로.
    far_from_any_station: bool


class LookupLandmark:
    def __init__(self, areas: AreaMetricsRepository, geocoder: LandmarkGeocoder) -> None:
        self._areas = areas
        self._geocoder = geocoder

    def execute(self, query: str) -> list[LandmarkCandidate]:
        matches = self._geocoder.search(query, limit=MAX_MATCHES)
        stations = self._areas.stations()
        return [self._with_nearest_station(match, stations) for match in matches]

    def _with_nearest_station(
        self, match: LandmarkMatch, stations: Sequence[Station]
    ) -> LandmarkCandidate:
        nearest: NearestStation | None = None
        for station in stations:
            d = distance_meters(match.lat, match.lon, station.lat, station.lon)
            if nearest is None or d < nearest.distance_m:
                nearest = NearestStation(station=station, distance_m=d)
        far = nearest is None or nearest.distance_m > FAR_FROM_STATION_M
        return LandmarkCandidate(match=match, nearest_station=nearest, far_from_any_station=far)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/application/test_lookup_landmark.py -v`
Expected: PASS (5개 테스트)

- [ ] **Step 5: lint/type check**

Run: `cd backend && uv run ruff check . && uv run mypy src`
Expected: 에러 없음

- [ ] **Step 6: 커밋**

```bash
cd backend
git add src/chika/application/usecase/lookup_landmark.py tests/application/test_lookup_landmark.py
git commit -m "feat(application): LookupLandmark 유스케이스 추가(가장 가까운 역 계산)"
```

---

### Task 5: 에이전트 배선 — state/actions/tools/prompts + 합성 루트(cli.py) + 기존 테스트 헬퍼 수정

**Files:**
- Modify: `backend/src/chika/interface/agent/state.py`
- Modify: `backend/src/chika/interface/agent/actions.py`
- Modify: `backend/src/chika/interface/agent/tools.py`
- Modify: `backend/src/chika/interface/agent/prompts.py`
- Modify: `backend/src/chika/interface/cli.py`
- Modify: `backend/tests/interface/test_agent_actions.py`(기존 `UseCases(...)` 호출부 4곳 수정 + `act_lookup_landmark` 테스트 추가)

**Interfaces:**
- Consumes: `LookupLandmark`(Task 4), `NominatimGeocoder`(Task 3),
  `NominatimClient`(Task 2), `NominatimFetchError`(Task 2), `OSM_ATTRIBUTION`(기존
  `actions.py` 613번째 줄 상수).
- Produces: `UseCases.lookup_landmark` 필드, `act_lookup_landmark(state, name) ->
  dict`, agent 툴 `lookup_landmark`.

이 태스크는 `UseCases`에 **필수 필드**를 추가하므로, 그 필드를 만드는 이 저장소의
모든 `UseCases(...)` 호출부(총 6곳: `cli.py` 2곳, `test_agent_actions.py` 4곳)를
한 커밋 안에서 같이 고쳐야 테스트가 깨지는 중간 상태가 생기지 않는다.

- [ ] **Step 1: `state.py`에 필드 추가**

`backend/src/chika/interface/agent/state.py` 수정 — import 블록에 추가:

```python
from chika.application.usecase.lookup_landmark import LookupLandmark
```

(`from chika.application.usecase.hazard_polygons import HazardPolygons` 다음 줄,
알파벳순.)

`UseCases` 클래스 끝(`new_construction: NewConstructionSearch` 다음)에 추가:

```python
    #: 랜드마크 이름 → 좌표 → 가장 가까운 역. lookup_station이 못 찾을 때
    #: 이어서 쓴다(lookup_landmark.py 참고).
    lookup_landmark: LookupLandmark
```

- [ ] **Step 2: `actions.py`에 `act_lookup_landmark` 추가**

`backend/src/chika/interface/agent/actions.py` 수정 — import 블록에서
`from chika.etl.mlit_client import MlitApiError` 다음 줄에 추가:

```python
from chika.etl.nominatim_client import NominatimFetchError
```

(`from chika.etl.overpass_client import OverpassFetchError` 앞 — 알파벳순
`nominatim_client` < `overpass_client`.)

`MAX_LOOKUP_MATCHES = 10`과 `act_lookup_station` 함수 바로 다음에 추가:

```python
def act_lookup_landmark(state: SessionState, name: str) -> dict[str, Any]:
    """랜드마크/지명 이름으로 좌표와 가장 가까운 역을 찾는다.

    lookup_station이 못 찾을 때(역이 아닌 공원·랜드마크·관광지 등) 이어서
    쓴다. 반환된 nearest_station.station_id를 explain_area 등에 그대로
    넘기면 된다. far_from_any_station이 true면 그 사실을 반드시 답변에
    밝힌다 — 조용히 먼 역 데이터를 그 지점 것처럼 말하지 않는다.
    """
    query = name.strip()
    if not query:
        return {"query": name, "matches": []}
    try:
        candidates = state.usecases.lookup_landmark.execute(query)
    except NominatimFetchError as exc:
        return {"error": "geocoder_unavailable", "detail": str(exc)}

    return {
        "query": query,
        "attribution": OSM_ATTRIBUTION,
        "matches": [
            {
                "name": c.match.name,
                "lat": c.match.lat,
                "lon": c.match.lon,
                "nearest_station": (
                    {
                        "station_id": c.nearest_station.station.id,
                        "name_ja": c.nearest_station.station.name_ja,
                        "distance_m": round(c.nearest_station.distance_m, 1),
                    }
                    if c.nearest_station is not None
                    else None
                ),
                "far_from_any_station": c.far_from_any_station,
            }
            for c in candidates
        ],
    }
```

`OSM_ATTRIBUTION`은 이미 613번째 줄 근처에 정의돼 있다 — 새로 만들지 않는다.

- [ ] **Step 3: `tools.py`에 `lookup_landmark` 툴 추가**

`backend/src/chika/interface/agent/tools.py` 수정 — `lookup_station` 함수
바로 다음에 추가:

```python
@function_tool
def lookup_landmark(ctx: RunContextWrapper[SessionState], name: str) -> dict[str, Any]:
    """역이 아닌 지명(공원·랜드마크·관광지 등)으로 좌표와 가장 가까운 역을
    찾는다. lookup_station이 못 찾았을 때 이어서 쓴다. 결과의
    nearest_station.station_id를 explain_area 등에 그대로 넘긴다.
    far_from_any_station이 true면 그 사실을 답변에 반드시 밝힌다.
    """
    return actions.act_lookup_landmark(ctx.context, name)
```

새 툴을 에이전트에 등록한다 — `backend/src/chika/interface/agent/agents.py` 수정.
`from chika.interface.agent.tools import (` import 블록의 `lookup_station,`
다음 줄에 `lookup_landmark,`를 추가하고(알파벳순), `AnalysisAgent`의
`tools=[...]` 리스트에서 `lookup_station,` 다음 줄에 `lookup_landmark,`를
추가한다:

```python
from chika.interface.agent.tools import (
    compare_areas,
    explain_area,
    explain_new_construction,
    hazard_polygons,
    lookup_landmark,
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
```

```python
        tools=[
            rank_areas,
            lookup_station,
            lookup_landmark,
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
```

- [ ] **Step 4: `prompts.py`에 규칙 추가**

`backend/src/chika/interface/agent/prompts.py` 수정 — `"lookup_station 이
0건을 돌려주면 그때만 \"도쿄 23구 데이터에 없는 역\"이라고"`로 시작하는 문단
(642번째 줄 근처) 바로 다음에 추가:

```
역이 아닌 지명(공원·랜드마크·관광지 등)을 말했다고 판단되면, 또는
lookup_station 이 0건을 돌려줬다면 lookup_landmark 를 이어서 시도합니다.
후보가 여럿이면 문맥상 가장 그럴듯한 것을 고르거나 사용자에게 확인합니다.
찾은 matches[].nearest_station.station_id 를 explain_area 등에 그대로
넘기면 됩니다. far_from_any_station 이 true인 후보를 쓸 때는 반드시
"가장 가까운 역이 실제로는 좀 떨어져 있다"는 사실을 답변에서 밝힙니다.
```

- [ ] **Step 5: `cli.py`의 두 합성 루트에 배선**

`backend/src/chika/interface/cli.py` 수정 — import 블록을 정확히 이렇게
고친다(추가되는 줄에 표시):

```python
from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.hazard_polygons import HazardPolygons
from chika.application.usecase.lookup_landmark import LookupLandmark  # 추가
from chika.application.usecase.metric_distribution import MetricDistribution
from chika.application.usecase.metric_extremes import MetricExtremes
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.application.usecase.park_polygons import ParkPolygons
from chika.application.usecase.rank_areas import RankAreas
from chika.application.usecase.school_facilities import SchoolFacilities
from chika.application.usecase.ward_price import WardPriceRanking
from chika.application.usecase.zoning_massing import ZoningMassing
from chika.etl.lazy_new_construction import ensure_ward_crawled
from chika.etl.mlit_client import MlitClient
from chika.etl.nominatim_client import NominatimClient  # 추가
from chika.etl.overpass_client import OverpassClient
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.infrastructure.file_metrics import FileAreaMetricsRepository
from chika.infrastructure.file_new_construction import FileNewConstructionRepository
from chika.infrastructure.mlit_hazard_source import MlitHazardPolygonSource
from chika.infrastructure.mlit_school_source import MlitSchoolFacilitySource
from chika.infrastructure.mlit_zoning_source import MlitZoningPolygonSource
from chika.infrastructure.nominatim_geocoder import NominatimGeocoder  # 추가
from chika.infrastructure.overpass_park_source import OverpassParkSource
from chika.interface.agent.actions import act_explain_area, act_rank_areas, act_set_criteria
from chika.interface.agent.state import SessionState, UseCases
```

`build_demo_session`과 `build_real_session` 양쪽의 `UseCases(...)` 안,
`new_construction=NewConstructionSearch(...)` 다음 줄에 각각 추가:

```python
            lookup_landmark=LookupLandmark(areas, NominatimGeocoder(NominatimClient())),
```

- [ ] **Step 6: 기존 테스트 헬퍼 4곳에 페이크 배선**

`backend/tests/interface/test_agent_actions.py` 수정.

파일 맨 위 import 블록을 정확히 이렇게 고친다(추가되는 줄에 표시):

```python
from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.hazard_polygons import HazardPolygons
from chika.application.usecase.lookup_landmark import LookupLandmark  # 추가
from chika.application.usecase.metric_distribution import MetricDistribution
from chika.application.usecase.metric_extremes import MetricExtremes
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.application.usecase.park_polygons import ParkPolygons
from chika.application.usecase.rank_areas import RankAreas
from chika.application.usecase.school_facilities import SchoolFacilities
from chika.application.usecase.ward_price import WardPriceRanking
from chika.application.usecase.zoning_massing import ZoningMassing
from chika.domain.model.criteria import Household
from chika.domain.model.facility import SchoolFacility
from chika.domain.model.landmark import LandmarkMatch  # 추가
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.new_construction import NewConstructionListing
from chika.domain.model.polygon import HazardPolygon, ParkPolygon, ZoningPolygon
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial
from chika.etl.mlit_client import MlitApiError
from chika.etl.nominatim_client import NominatimFetchError  # 추가
from chika.etl.overpass_client import OverpassFetchError
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.actions import (
    act_compare_areas,
    act_explain_area,
    act_explain_new_construction,
    act_hazard_polygons,
    act_lookup_landmark,  # 추가
    act_lookup_new_construction,
    act_lookup_station,
    act_metric_distribution,
    act_metric_extremes,
    act_park_polygons,
    act_rank_areas,
    act_school_facilities,
    act_search_new_construction,
    act_set_criteria,
    act_ward_price_ranking,
    act_zoning_massing,
)
from chika.interface.agent.state import SessionState, UseCases
```

다음 `_FakeParkPolygonSource` 클래스 정의 바로 다음에 페이크 지오코더를
추가한다:

```python
class _FakeLandmarkGeocoder:
    """`LandmarkGeocoder` 포트의 테스트 더블. 실제 Nominatim 호출이 없다."""

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        return []
```

그 다음 `UseCases(...)`를 만드는 4곳
(`_deterministic_state`/`state` fixture/`_state_with_sources`/
`_state_with_park_source`) 전부에서, `new_construction=NewConstructionSearch(...)`
다음 줄에 다음을 추가:

```python
            lookup_landmark=LookupLandmark(areas, _FakeLandmarkGeocoder()),
```

- [ ] **Step 7: `act_lookup_landmark`의 새 테스트 작성**

`test_agent_actions.py`의 "역 이름으로 찾기" 섹션(`test_lookup_finds_a_station_...`
근처) 다음에 새 섹션 추가:

```python
# --- 랜드마크 이름으로 찾기 ---


class _FakeLandmarkGeocoderWith:
    def __init__(self, matches: list[LandmarkMatch]) -> None:
        self._matches = matches

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        return self._matches


class _RaisingLandmarkGeocoder:
    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        raise NominatimFetchError("HTTP 503")


def _state_with_landmark_geocoder(geocoder) -> SessionState:  # noqa: ANN001
    stations = [_station("a", name_ja="光が丘", ward="練馬区")]
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
            school_facilities=SchoolFacilities(_FakeSchoolFacilitySource()),
            park_polygons=ParkPolygons(_FakeParkPolygonSource()),
            new_construction=NewConstructionSearch(_FakeNewConstructionRepo([])),
            lookup_landmark=LookupLandmark(areas, geocoder),
        )
    )


def test_lookup_landmark_returns_the_nearest_station_for_each_match() -> None:
    match = LandmarkMatch(name="光が丘公園", lat=35.7585, lon=139.6295)
    state = _state_with_landmark_geocoder(_FakeLandmarkGeocoderWith([match]))

    result = act_lookup_landmark(state, "히카리가오카 공원")

    assert result["matches"][0]["name"] == "光が丘公園"
    assert result["matches"][0]["nearest_station"]["station_id"] == "a"
    assert result["attribution"] == "© OpenStreetMap contributors"


def test_lookup_landmark_returns_no_matches_when_the_query_is_blank() -> None:
    state = _state_with_landmark_geocoder(_FakeLandmarkGeocoderWith([]))
    result = act_lookup_landmark(state, "   ")
    assert result["matches"] == []


def test_lookup_landmark_reports_geocoder_unavailable_on_error() -> None:
    state = _state_with_landmark_geocoder(_RaisingLandmarkGeocoder())
    result = act_lookup_landmark(state, "아무 지명")
    assert result["error"] == "geocoder_unavailable"
```

(`act_lookup_landmark`와 `NominatimFetchError`는 Step 6에서 이미 import
블록에 추가했다 — 여기서 다시 추가할 필요 없다.)

- [ ] **Step 8: 백엔드 테스트 전체 통과 확인**

Run: `cd backend && uv run pytest -v`
Expected: PASS(기존 전체 + 이번에 추가한 테스트 전부, 회귀 없음)

- [ ] **Step 9: lint/type check**

Run: `cd backend && uv run ruff check . && uv run mypy src`
Expected: 에러 없음

- [ ] **Step 10: 커밋**

```bash
cd backend
git add src/chika/interface/agent/state.py src/chika/interface/agent/actions.py \
  src/chika/interface/agent/tools.py src/chika/interface/agent/prompts.py \
  src/chika/interface/agent/agents.py src/chika/interface/cli.py \
  tests/interface/test_agent_actions.py
git commit -m "feat(agent): lookup_landmark 툴 배선 — 랜드마크 이름으로 가장 가까운 역 찾기"
```

---

### Task 6: 라이브 검증 (수동, 자동화된 테스트 없음)

**Files:** 없음 — 백엔드 서버를 띄워 실제 Nominatim 호출을 확인하는 수동 검증
태스크다.

- [ ] **Step 1: 올바른 엔트리포인트로 백엔드 기동**

Run: `cd backend && python -m chika.interface.api`
(잘못된 uvicorn 엔트리포인트나 포트 충돌로 예전에 두 번 헛수고한 적이 있다 —
`lsof -i :8000`으로 실제로 이 프로세스가 응답하는지 먼저 확인한다.)

- [ ] **Step 2: 랜드마크 질의로 curl 테스트**

Run:
```bash
curl -s -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"landmark-verify-1","message":"신주쿠교엔 근처 살기 좋아?"}'
```
Expected: SSE 스트림에 `lookup_landmark` 툴 이벤트가 나오고, 이어서
`explain_area`(또는 그에 준하는 분석 흐름)가 신주쿠 인근 역의 station_id로
호출되며, 텍스트 응답이 "신주쿠御苑" 관련 역 기준 분석을 담고 있다.

- [ ] **Step 3: 먼 지점 질의로 경고 문구 확인**

도쿄 23구 데이터 범위 밖(예: 존재하지만 489역에서 아주 먼) 지명으로 같은
방식 curl — 응답 텍스트에 "가장 가까운 역이 실제로는 좀 떨어져 있다"는
취지의 경고가 포함되는지 확인한다.

- [ ] **Step 4: 결과를 사용자에게 보고**

두 질의의 SSE 이벤트/텍스트 요약을 대화에 공유한다. 문제가 있으면 프롬프트
규칙(Task 5 Step 4)을 조정하고 재검증한다.
