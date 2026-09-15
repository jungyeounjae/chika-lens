# 학교/보육시설 3D 시각화 실시간 조회 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 좌표(lat/lon) 하나를 주면 그 주변 학교/보육시설을 실시간으로 조회해 3D 마커 시각화 재료(이름·종별·좌표·거리)를 돌려주는 에이전트 툴을 추가한다.

**Architecture:** `hazard_polygons`/`zoning_massing`과 완전히 같은 4계층 실시간 조회 패턴(domain 포트 → infrastructure MLIT 어댑터 → application usecase → interface 4단 배선)이되, `station_id` 대신 좌표를 직접 받는다는 점만 다르다. 파싱 로직(`etl/mlit_childcare.py`의 `parse_preschool`/`parse_school`/`deduplicate`)은 기존 지표 11(육아·교육) 배치가 이미 검증해 둔 것을 그대로 재사용한다 — 새로 만들지 않는다.

**Tech Stack:** 기존 스택 그대로(Python 3.12, MLIT `不動産情報ライブラリ` XKT006/XKT007). 새 외부 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-09-14-school-facilities-3d-design.md`

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과, `mypy --strict` 통과(프로젝트 컨벤션: `uv run mypy src`).
- domain 계층은 `etl`/`infrastructure`를 몰라야 한다 — `etl.mlit_childcare.Facility`를 domain에서 재사용하지 않는다. `domain/model/facility.py`에 별도 `SchoolFacility` 값 객체를 새로 정의하고, infrastructure 어댑터가 etl의 `Facility`를 이 타입으로 변환한다.
- `UseCases`(`interface/agent/state.py`)는 `frozen=True` dataclass라 필드 하나를 추가하면 **모든 생성 지점**을 고쳐야 한다 — 2026-09-14 기준 정확히 6곳: `backend/src/chika/interface/cli.py:65`(`build_demo_session`), `cli.py:124`(`build_real_session`), `backend/tests/interface/test_agent_actions.py:120`(`_deterministic_state`), `:141`(`state` fixture), `:1026`(`_state_with_sources`), `:1132`(`_state_with_new_construction`). 하나라도 빠뜨리면 그 파일의 다른 테스트가 `TypeError: missing argument`로 전부 깨진다.
- 반경 상한을 클램프한다(사용자가 반경을 비정상적으로 크게 주면 타일 요청이 폭증한다) — `hazard_polygons`의 `_MAX_POLYGON_RADIUS_M`과 같은 이유.
- 결과 0건은 에러가 아니다 — "이 반경 안에 학교 없음"은 정상 응답.
- MLIT 호출 실패(`MlitApiError`)는 `{"error": "mlit_unavailable", "detail": ...}` dict로 반환하지, 예외를 그대로 올리지 않는다(기존 `act_hazard_polygons`와 동일한 계약).

## 사전 조사 결과 (재사용할 기존 코드)

- `etl/mlit_childcare.py`: `Facility(facility_id, lat, lon, kind, name)`, `parse_preschool(feature) -> Facility | None`(XKT007, 폐원 제외), `parse_school(feature) -> Facility | None`(XKT006, `SCHOOL_KINDS_COUNTED` = 초등·중학·義務教育学校만), `deduplicate(facilities) -> list[Facility]`(타일 경계 중복 제거).
- `etl/mlit_client.py`: `tiles_covering(points, zoom, margin_m)` — `mlit_hazard_source.py`가 이미 `tiles_covering([(lat, lon)], dataset.zoom, radius_m)` 형태로 쓴다. `MlitClient.features(dataset, x, y) -> Sequence[dict]`.
- `etl/mlit_datasets.py`: `PRESCHOOL = MlitDataset("XKT007", ...)`, `SCHOOL = MlitDataset("XKT006", ...)`.
- `domain/service/geo.py`: `distance_meters(lat1, lon1, lat2, lon2) -> float`.
- `infrastructure/mlit_hazard_source.py`가 이 모든 조각을 조합하는 정확한 선례다 — Task 2는 이 파일의 구조를 그대로 따른다.
- `interface/agent/actions.py:617`의 `act_hazard_polygons`가 반경 클램프 + `MlitApiError` 처리의 정확한 선례다.

---

## Task 1: 도메인 값 객체 + 리포지토리 포트

**Files:**
- Create: `backend/src/chika/domain/model/facility.py`
- Modify: `backend/src/chika/domain/repository.py`
- Test: `backend/tests/domain/model/test_facility.py`

**Interfaces:**
- Produces: `SchoolFacility(facility_id: str, name: str, kind: str, lat: float, lon: float, distance_m: float)`(frozen dataclass), `SchoolFacilitySource` Protocol(`facilities_near(lat: float, lon: float, radius_m: float) -> Sequence[SchoolFacility]`). Task 2(infrastructure)·Task 3(usecase)·Task 4(agent)가 이 타입들을 그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/domain/model/test_facility.py
"""SchoolFacility 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.facility import SchoolFacility


def test_a_facility_can_be_constructed_with_all_fields() -> None:
    facility = SchoolFacility(
        facility_id="f_12345",
        name="光が丘第八小学校",
        kind="小学校",
        lat=35.7601,
        lon=139.6089,
        distance_m=312.4,
    )
    assert facility.name == "光が丘第八小学校"
    assert facility.kind == "小学校"
    assert facility.distance_m == 312.4
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_facility.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.facility'`

- [ ] **Step 3: `domain/model/facility.py` 구현**

```python
# backend/src/chika/domain/model/facility.py
"""3D 시각화용 시설 값 객체 — etl 배치 산출물이 아니라 요청 단위 실시간 조회 결과.

etl.mlit_childcare.Facility 와 필드가 겹치지만 별개 타입이다 — domain 은 etl 을
몰라야 한다(Clean Architecture, README "계층 규칙"). infrastructure 어댑터
(MlitSchoolFacilitySource, Task 2)가 변환한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchoolFacility:
    facility_id: str
    name: str
    #: 유치원/보육시설 종별 또는 "小学校"/"中学校"/"義務教育学校" 원문 그대로
    #: (mlit_childcare.py 의 kind 를 그대로 옮긴다 — 지어내지 않는다).
    kind: str
    lat: float
    lon: float
    #: 조회 좌표로부터의 거리(m). NewConstructionQuietness.distance_m 과 같은
    #: 선례로 값 객체 안에 포함시킨다 — 정렬·표시에 바로 쓸 수 있게.
    distance_m: float
```

- [ ] **Step 4: `domain/repository.py`에 포트 추가**

`backend/src/chika/domain/repository.py`의 import 블록에 추가(기존
`from chika.domain.model.criteria import ...` 근처, 알파벳 순서에 맞게):

```python
from chika.domain.model.facility import SchoolFacility
```

파일 맨 끝에 새 Protocol을 추가한다:

```python
class SchoolFacilitySource(Protocol):
    """학교/보육시설 3D 시각화 포트. 요청 단위 실시간 조회 — 배치가 아니다."""

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> Sequence[SchoolFacility]: ...
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_facility.py -v`
Expected: PASS (1 passed)

Run also: `cd backend && uv run pytest -q` (전체 스위트가 여전히 통과하는지 —
`domain/repository.py` import 추가가 다른 곳을 깨지 않는지 확인. `SchoolFacilitySource`를
아직 아무도 구현/소비하지 않으므로 새 실패는 없어야 한다.)

- [ ] **Step 6: 커밋**

```bash
git add backend/src/chika/domain/model/facility.py backend/src/chika/domain/repository.py backend/tests/domain/model/test_facility.py
git commit -m "feat(domain): 학교/보육시설 값 객체 + 리포지토리 포트 추가"
```

---

## Task 2: MLIT 실시간 조회 인프라

**Files:**
- Create: `backend/src/chika/infrastructure/mlit_school_source.py`
- Test: `backend/tests/infrastructure/test_mlit_school_source.py`

**Interfaces:**
- Consumes: `SchoolFacility`(Task 1), `etl/mlit_childcare.py`의 `parse_preschool`/`parse_school`/`deduplicate`(기존), `etl/mlit_client.py`의 `MlitClient`/`tiles_covering`(기존), `etl/mlit_datasets.py`의 `PRESCHOOL`/`SCHOOL`(기존).
- Produces: `MlitSchoolFacilitySource(client: MlitClient)`, `.facilities_near(lat: float, lon: float, radius_m: float) -> list[SchoolFacility]`. Task 4가 이 클래스를 `cli.py`에서 인스턴스화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/infrastructure/test_mlit_school_source.py
"""MlitSchoolFacilitySource — 실시간 MLIT 조회(XKT006/XKT007) + 거리 필터링."""

from __future__ import annotations

import json

from chika.etl.mlit_client import MlitClient
from chika.infrastructure.mlit_school_source import MlitSchoolFacilitySource

#: 조회 좌표 — 光が丘역 근방(実測 주소는 아니고 테스트용 임의 좌표).
QUERY_LAT, QUERY_LON = 35.760, 139.609
NEAR_LAT, NEAR_LON = 35.7605, 139.6095  # QUERY 로부터 약 70m
FAR_LAT, FAR_LON = 35.90, 139.90  # 수십km 밖


def _preschool_feature(
    facility_id: str, name: str, lat: float = NEAR_LAT, lon: float = NEAR_LON
) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "_id": facility_id,
            "schoolClassCode_name_ja": "幼稚園",
            "preSchoolName_ja": name,
        },
    }


def _school_feature(
    facility_id: str, name: str, kind: str = "小学校", lat: float = NEAR_LAT, lon: float = NEAR_LON
) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"_id": facility_id, "P29_003_name_ja": kind, "P29_004_ja": name},
    }


def _client_returning(features_by_endpoint: dict[str, list[dict[str, object]]]) -> MlitClient:
    def transport(url: str, _headers: dict[str, str]) -> tuple[bytes, str]:
        for endpoint, features in features_by_endpoint.items():
            if f"/{endpoint}" in url:
                return json.dumps({"type": "FeatureCollection", "features": features}).encode(), ""
        return json.dumps({"type": "FeatureCollection", "features": []}).encode(), ""

    return MlitClient("test-key", transport=transport, sleep=lambda _: None)


def test_a_preschool_near_the_point_is_returned_with_distance() -> None:
    client = _client_returning({"XKT007": [_preschool_feature("p1", "ひかり幼稚園")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1
    assert facilities[0].name == "ひかり幼稚園"
    assert facilities[0].kind == "幼稚園"
    assert facilities[0].distance_m < 800.0


def test_a_school_near_the_point_is_returned() -> None:
    client = _client_returning({"XKT006": [_school_feature("s1", "光が丘第八小学校")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1
    assert facilities[0].name == "光が丘第八小学校"
    assert facilities[0].kind == "小学校"


def test_a_facility_far_beyond_the_radius_is_dropped() -> None:
    client = _client_returning(
        {"XKT006": [_school_feature("s1", "먼학교", lat=FAR_LAT, lon=FAR_LON)]}
    )
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert facilities == []


def test_a_high_school_is_excluded_not_zero() -> None:
    """SCHOOL_KINDS_COUNTED(초등·중학·義務教育学校)만 센다 — parse_school의 기존
    동작을 그대로 물려받는다(mlit_childcare.py 기존 로직, 새로 만드는 필터가
    아니다)."""
    client = _client_returning({"XKT006": [_school_feature("s1", "고교", kind="高等学校")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert facilities == []


def test_duplicate_features_across_tiles_are_deduplicated_by_id() -> None:
    feature = _preschool_feature("dup", "중복유치원")
    client = _client_returning({"XKT007": [feature, feature]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1


def test_preschools_and_schools_are_combined_and_sorted_by_distance() -> None:
    close = _preschool_feature("p1", "가까운유치원", lat=NEAR_LAT, lon=NEAR_LON)
    far_but_in_radius = _school_feature(
        "s1", "먼학교", lat=QUERY_LAT + 0.003, lon=QUERY_LON + 0.003
    )
    client = _client_returning({"XKT007": [close], "XKT006": [far_but_in_radius]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert [f.name for f in facilities] == ["가까운유치원", "먼학교"]
    assert facilities[0].distance_m < facilities[1].distance_m
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/infrastructure/test_mlit_school_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.infrastructure.mlit_school_source'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/infrastructure/mlit_school_source.py
"""`SchoolFacilitySource` 포트의 실제 구현 — MLIT 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와 같은
구조다 — 배치가 아니라 요청 한 건을 위해 MLIT 을 실시간으로 호출한다(호출
과금 없음). 파싱은 etl.mlit_childcare 의 기존 함수를 그대로 재사용한다.
"""

from __future__ import annotations

from chika.domain.model.facility import SchoolFacility
from chika.domain.service.geo import distance_meters
from chika.etl.mlit_childcare import deduplicate, parse_preschool, parse_school
from chika.etl.mlit_client import MlitClient, tiles_covering
from chika.etl.mlit_datasets import PRESCHOOL, SCHOOL


class MlitSchoolFacilitySource:
    def __init__(self, client: MlitClient) -> None:
        self._client = client

    def facilities_near(self, lat: float, lon: float, radius_m: float) -> list[SchoolFacility]:
        preschool_raw: list[dict[str, object]] = []
        school_raw: list[dict[str, object]] = []
        for dataset, sink in ((PRESCHOOL, preschool_raw), (SCHOOL, school_raw)):
            for x, y in tiles_covering([(lat, lon)], dataset.zoom, radius_m):
                sink.extend(self._client.features(dataset, x, y))

        preschools = deduplicate(f for item in preschool_raw if (f := parse_preschool(item)))
        schools = deduplicate(f for item in school_raw if (f := parse_school(item)))

        result: list[SchoolFacility] = []
        for facility in [*preschools, *schools]:
            distance = distance_meters(lat, lon, facility.lat, facility.lon)
            if distance > radius_m:
                continue
            result.append(
                SchoolFacility(
                    facility_id=facility.facility_id,
                    name=facility.name,
                    kind=facility.kind,
                    lat=facility.lat,
                    lon=facility.lon,
                    distance_m=round(distance, 1),
                )
            )
        result.sort(key=lambda f: f.distance_m)
        return result
```

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/infrastructure/test_mlit_school_source.py -v` — 6 passed 기대.
Run: `cd backend && uv run ruff check src/chika/infrastructure/mlit_school_source.py tests/infrastructure/test_mlit_school_source.py && uv run mypy src/chika/infrastructure/mlit_school_source.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/infrastructure/mlit_school_source.py backend/tests/infrastructure/test_mlit_school_source.py
git commit -m "feat(infra): 학교/보육시설 MLIT 실시간 조회 인프라 추가"
```

---

## Task 3: 검색 유스케이스

**Files:**
- Create: `backend/src/chika/application/usecase/school_facilities.py`
- Test: `backend/tests/application/test_school_facilities.py`

**Interfaces:**
- Consumes: `SchoolFacilitySource`(Task 1 포트), `SchoolFacility`(Task 1).
- Produces: `SchoolFacilities(source: SchoolFacilitySource)`, `.execute(lat: float, lon: float, radius_m: float = 800.0) -> list[SchoolFacility]`. Task 4가 이 클래스를 `UseCases`에 넣고 `actions.py`에서 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/application/test_school_facilities.py
"""SchoolFacilities 유스케이스 — 포트(SchoolFacilitySource)에 위임할 뿐임을 확인한다."""

from __future__ import annotations

from chika.application.usecase.school_facilities import SchoolFacilities
from chika.domain.model.facility import SchoolFacility


class _StubSource:
    def __init__(self, facilities: list[SchoolFacility]) -> None:
        self._facilities = facilities
        self.calls: list[tuple[float, float, float]] = []

    def facilities_near(self, lat: float, lon: float, radius_m: float) -> list[SchoolFacility]:
        self.calls.append((lat, lon, radius_m))
        return self._facilities


def test_execute_forwards_coordinates_and_radius_to_the_source() -> None:
    source = _StubSource([])
    usecase = SchoolFacilities(source)

    usecase.execute(35.76, 139.61, radius_m=900.0)

    assert source.calls == [(35.76, 139.61, 900.0)]


def test_execute_uses_800m_as_the_default_radius() -> None:
    source = _StubSource([])
    usecase = SchoolFacilities(source)

    usecase.execute(35.76, 139.61)

    assert source.calls == [(35.76, 139.61, 800.0)]


def test_execute_returns_the_sources_facilities() -> None:
    facility = SchoolFacility(
        facility_id="f1", name="光が丘第八小学校", kind="小学校",
        lat=35.76, lon=139.61, distance_m=120.0,
    )
    usecase = SchoolFacilities(_StubSource([facility]))

    result = usecase.execute(35.76, 139.61)

    assert result == [facility]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/application/test_school_facilities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.school_facilities'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/application/usecase/school_facilities.py
"""학교/보육시설 실시간 조회 — 3D 시각화 재료. hazard_polygons.py 와 같은 구조.

station_id 가 아니라 좌표를 직접 받는다 — 역(rank_areas)이든 신축 물건
(search_new_construction)이든 lat/lon 만 있으면 동작해야 하기 때문이다.
"""

from __future__ import annotations

from chika.domain.model.facility import SchoolFacility
from chika.domain.repository import SchoolFacilitySource

RADIUS_M = 800.0  # 기존 지표 11(육아·교육)의 역세권 반경과 동일(STATION_RADIUS_METERS)


class SchoolFacilities:
    def __init__(self, source: SchoolFacilitySource) -> None:
        self._source = source

    def execute(self, lat: float, lon: float, radius_m: float = RADIUS_M) -> list[SchoolFacility]:
        return list(self._source.facilities_near(lat, lon, radius_m))
```

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/application/test_school_facilities.py -v` — 3 passed 기대.
Run: `cd backend && uv run ruff check src/chika/application/usecase/school_facilities.py tests/application/test_school_facilities.py && uv run mypy src/chika/application/usecase/school_facilities.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/application/usecase/school_facilities.py backend/tests/application/test_school_facilities.py
git commit -m "feat(application): 학교/보육시설 실시간 조회 유스케이스 추가"
```

---

## Task 4: 에이전트 툴 배선 (state/actions/tools/agents/prompts/cli)

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
- Consumes: `SchoolFacilities`(Task 3), `MlitSchoolFacilitySource`(Task 2), `SchoolFacility`(Task 1).
- Produces: `act_school_facilities`(actions.py) → `school_facilities`(tools.py, `@function_tool`) → `AnalysisAgent`에 등록.

- [ ] **Step 1: `state.py` 수정**

`backend/src/chika/interface/agent/state.py`의 import 블록에 추가:

```python
from chika.application.usecase.school_facilities import SchoolFacilities
```

`UseCases`의 `zoning_massing` 필드 바로 뒤에 추가:

```python
    #: 학교/보육시설 3D 시각화용 — 배치가 아니라 요청 단위 실시간 MLIT 호출이다
    #: (school_facilities.py 참고). 좌표 기반이라 역이든 신축 물건이든 쓴다.
    school_facilities: SchoolFacilities
```

- [ ] **Step 2: `actions.py`에 함수 추가**

파일 맨 끝(`act_lookup_new_construction` 함수 뒤, 또는 새 신축 관련 함수들
뒤)에 추가:

```python
#: 한 번에 LLM 에 넘기는 시설 상한 — 밀집 지역에서 payload 가 과하게
#: 커지는 걸 막는다. 거리순 정렬 후 자르므로 가까운 곳부터 남는다.
MAX_SCHOOL_FACILITIES_LIMIT = 20
_MAX_SCHOOL_RADIUS_M = 1500.0  # 도보 통학권(초등~중학) 밖은 의미 없음


def act_school_facilities(
    state: SessionState, lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 하나 주변의 학교/보육시설 — 3D 마커 시각화 재료.

    hazard_polygons 와 같은 이유로 요청마다 MLIT 을 실시간 호출한다(호출
    과금 없음, 489역 전체가 아니라 사용자가 지목한 좌표 하나에만 쓴다).
    """
    radius = max(1.0, min(radius_m, _MAX_SCHOOL_RADIUS_M))
    try:
        facilities = state.usecases.school_facilities.execute(lat, lon, radius_m=radius)
    except MlitApiError as exc:
        return {"error": "mlit_unavailable", "detail": str(exc)}

    capped = facilities[:MAX_SCHOOL_FACILITIES_LIMIT]
    return {
        "lat": lat,
        "lon": lon,
        "radius_m": radius,
        "facilities": [
            {
                "facility_id": f.facility_id,
                "name": f.name,
                "kind": f.kind,
                "lat": f.lat,
                "lon": f.lon,
                "distance_m": f.distance_m,
            }
            for f in capped
        ],
    }
```

`MlitApiError`는 이미 파일 상단에서 import 돼 있다(`from chika.etl.mlit_client
import MlitApiError`) — 추가 import 불필요.

- [ ] **Step 3: `tools.py`에 툴 추가**

파일 맨 끝(`explain_new_construction` 함수 뒤)에 추가:

```python
@function_tool
def school_facilities(
    ctx: RunContextWrapper[SessionState], lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 주변의 학교·유치원·보육시설 위치를 낸다 — 3D 지도 마커 재료.

    "아이 키우기 좋아?", "학교 가까워?", "이 동네 살기 좋아?"(교육 인프라
    맥락) 같은 질문에 쓴다. `lat`/`lon`은 `rank_areas`/`search_new_construction`
    결과에 이미 있는 좌표를 그대로 넘긴다 — 역이든 신축 물건이든 상관없다.

    결과가 0건이면 "이 반경 안에 학교/보육시설이 없다"는 뜻이지 조회 실패가
    아니다. `kind`는 원문 그대로(예: "小学校", "義務教育学校", 보육시설 종별) —
    한국어로 지어내 번역하지 않는다(자연스럽게 풀어서 설명하는 것은 괜찮다).
    """
    return actions.act_school_facilities(ctx.context, lat=lat, lon=lon, radius_m=radius_m)
```

- [ ] **Step 4: `agents.py`에 등록**

`from chika.interface.agent.tools import (...)` 블록에 `school_facilities`를
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
        ],
    )
    ...
```

(`...` 이하 `intake`/`return` 블록은 그대로 둔다.)

- [ ] **Step 5: `prompts.py`에 안내 문단 추가**

`ANALYSIS_INSTRUCTIONS` 안에서 `- **"신축", "분양", "모델하우스" 관련 질문은
search_new_construction ...` 문단(현재 484번째 줄 근처)이 시작되기 **직전**에
다음 문단을 새 bullet로 끼워 넣는다. 정확한 줄 번호는 구현 시점에
`grep -n '"신축", "분양"' backend/src/chika/interface/agent/prompts.py`로
재확인한다 — 이전 작업들이 이 파일에 여러 번 손을 대서 줄 번호가 계속
바뀌었다.

```
- **"아이 키우기 좋아?", "학교 가까워?" 같은 교육 인프라 질문은
  school_facilities.** `lat`/`lon`은 방금 조회한 역이나 신축 물건의 좌표를
  그대로 쓴다 — `rank_areas`/`search_new_construction` 결과에 이미 있다.
  결과 0건은 "이 반경 안에 학교 없음"이지 오류가 아니다 — 그렇게 답한다.
  `kind`는 원문(일본어) 그대로 나오니 자연스럽게 풀어서 설명한다(예:
  "小学校" → "초등학교", "義務教育学校" → "초중일관교").
```

- [ ] **Step 6: `cli.py` 수정**

파일 상단 import에 추가:

```python
from chika.application.usecase.school_facilities import SchoolFacilities
from chika.infrastructure.mlit_school_source import MlitSchoolFacilitySource
```

`build_demo_session`의 `UseCases(...)` 생성부에서, 기존
`hazard_polygons=HazardPolygons(areas, MlitHazardPolygonSource(client))` 바로
뒤에 추가(`client`는 함수 안에서 이미 `_mlit_client()`로 만들어져 있다):

```python
            school_facilities=SchoolFacilities(MlitSchoolFacilitySource(client)),
```

`build_real_session`도 같은 위치(`hazard_polygons=...` 바로 뒤)에 동일하게
추가한다.

- [ ] **Step 7: 기존 테스트 4곳에 `school_facilities` 필드 추가**

`backend/tests/interface/test_agent_actions.py`에서 `UseCases(` 생성이
4곳에 있다(2026-09-14 기준 line 120 `_deterministic_state`, line 141 `state`
fixture, line 1026 `_state_with_sources`, line 1132
`_state_with_new_construction`) — **각각의 `zoning_massing=...` 줄 바로
뒤에** 다음 한 줄을 추가한다:

```python
            school_facilities=SchoolFacilities(_FakeSchoolFacilitySource()),
```

이를 위해 파일 상단에 페이크 소스와 import를 추가한다. import 블록에:

```python
from chika.application.usecase.school_facilities import SchoolFacilities
from chika.domain.model.facility import SchoolFacility
```

`_FakeZoningPolygonSource` 클래스 뒤에 페이크 소스를 추가한다:

```python
class _FakeSchoolFacilitySource:
    """`SchoolFacilitySource` 포트의 테스트 더블. 실제 MLIT 호출이 없다."""

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[SchoolFacility]:
        return []
```

- [ ] **Step 8: 새 액션 테스트 추가**

같은 파일(`test_agent_actions.py`) 맨 끝에 추가:

```python
# --- school_facilities ---


class _FakeSchoolFacilitySourceWith:
    def __init__(self, facilities: list[SchoolFacility]) -> None:
        self._facilities = facilities

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[SchoolFacility]:
        return self._facilities


class _RaisingSchoolFacilitySource:
    """MLIT 서버 장애 시나리오 — `mlit_unavailable` 오류 처리를 검증한다."""

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[SchoolFacility]:
        raise MlitApiError("HTTP 503: 서버 오류")


def _state_with_school_source(source) -> SessionState:  # noqa: ANN001
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
            school_facilities=SchoolFacilities(source),
        )
    )


def test_school_facilities_returns_facilities_within_radius() -> None:
    facility = SchoolFacility(
        facility_id="f1", name="光が丘第八小学校", kind="小学校",
        lat=35.76, lon=139.61, distance_m=120.0,
    )
    session = _state_with_school_source(_FakeSchoolFacilitySourceWith([facility]))

    result = act_school_facilities(session, lat=35.76, lon=139.61)

    assert result["facilities"] == [
        {
            "facility_id": "f1",
            "name": "光が丘第八小学校",
            "kind": "小学校",
            "lat": 35.76,
            "lon": 139.61,
            "distance_m": 120.0,
        }
    ]


def test_school_facilities_returns_an_empty_list_when_none_are_nearby() -> None:
    session = _state_with_school_source(_FakeSchoolFacilitySourceWith([]))

    result = act_school_facilities(session, lat=35.76, lon=139.61)

    assert result["facilities"] == []


class _RecordingSchoolFacilitySource:
    """호출 인자를 기록하는 더블 — 반경 클램프가 usecase 까지 실제로
    전달되는지 확인하는 데 쓴다(빈 리스트만 돌려주면 클램프 여부를 검증할
    수 없다)."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float, float]] = []

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[SchoolFacility]:
        self.calls.append((lat, lon, radius_m))
        return []


def test_school_facilities_clamps_the_radius_to_the_maximum() -> None:
    source = _RecordingSchoolFacilitySource()
    session = _state_with_school_source(source)

    act_school_facilities(session, lat=35.76, lon=139.61, radius_m=999_999.0)

    assert source.calls == [(35.76, 139.61, 1500.0)]


def test_school_facilities_reports_mlit_unavailable_on_error() -> None:
    session = _state_with_school_source(_RaisingSchoolFacilitySource())

    result = act_school_facilities(session, lat=35.76, lon=139.61)

    assert result == {"error": "mlit_unavailable", "detail": "HTTP 503: 서버 오류"}
```

같은 파일 상단 import 블록에 `act_school_facilities`도 추가한다
(`from chika.interface.agent.actions import (...)` 블록, 알파벳 순서).

- [ ] **Step 9: `test_agent_wiring.py`의 정확 툴셋 단언 갱신**

`test_analysis_agent_exposes_the_analysis_tools`의 `assert set(...)` 블록
끝에 `"school_facilities"`를 추가한다:

```python
        "search_new_construction",
        "lookup_new_construction",
        "explain_new_construction",
        "school_facilities",
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
`UseCases` 필드 추가로 인한 4곳의 누락이 없는지 이 실행이 확인해 준다.

- [ ] **Step 11: 커밋**

```bash
git add backend/src/chika/interface/agent/state.py backend/src/chika/interface/agent/actions.py backend/src/chika/interface/agent/tools.py backend/src/chika/interface/agent/agents.py backend/src/chika/interface/agent/prompts.py backend/src/chika/interface/cli.py backend/tests/interface/test_agent_actions.py backend/tests/interface/test_agent_wiring.py
git commit -m "feat(agent): 학교/보육시설 실시간 조회 툴을 AnalysisAgent에 배선"
```

---

## Task 5: 실제 실행으로 수동 검증

- [ ] **Step 1: CLI 스크립트로 실좌표 조회 확인(OpenAI 키 불필요, MLIT 키 필요)**

```bash
cd backend
MLIT_API_KEY=<실제 키> uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_school_facilities

state = build_real_session()
# 光が丘역 근방 좌표(2026-09-14 세션에서 확인한 신축 물건 좌표 중 하나 사용 가능)
result = act_school_facilities(state, lat=35.760, lon=139.609, radius_m=800.0)
print(f'조회 결과 {len(result[\"facilities\"])}건')
for f in result['facilities'][:10]:
    print(f'  {f[\"name\"]} ({f[\"kind\"]}) · {f[\"distance_m\"]}m')
"
```

Expected: 학교/보육시설이 거리순으로 여러 건 나온다. 각 항목에 `name`·`kind`·
`distance_m`이 채워져 있고, `distance_m`이 `radius_m`(800) 이하여야 한다.

- [ ] **Step 2: 반경 밖/시설 없는 좌표에서 빈 결과 확인**

```bash
cd backend
MLIT_API_KEY=<실제 키> uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_school_facilities

state = build_real_session()
# 도쿄만 한가운데(육지가 아닌 좌표) — 학교가 있을 수 없다.
result = act_school_facilities(state, lat=35.60, lon=139.80, radius_m=300.0)
print(f'결과: {len(result[\"facilities\"])}건 (0건이어야 정상, 에러 아님)')
"
```

Expected: 예외 없이 `0건`(또는 실제로 뭔가 있으면 그 개수 — 핵심은 에러
없이 정상 응답한다는 것).

- [ ] **Step 3: 반경 상한 클램프 확인**

```bash
cd backend
MLIT_API_KEY=<실제 키> uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_school_facilities

state = build_real_session()
result = act_school_facilities(state, lat=35.760, lon=139.609, radius_m=99_999.0)
print(f'요청 반경 99999 -> 실제 사용된 반경: {result[\"radius_m\"]}')
assert result['radius_m'] == 1500.0
print('클램프 정상')
"
```

Expected: `실제 사용된 반경: 1500.0`, `클램프 정상` 출력.

---

## Self-Review 체크리스트

- **스펙 커버리지**: 스펙의 컴포넌트 5개(domain 값 객체+포트, infrastructure
  어댑터, application usecase, 에이전트 4단 배선, 테스트)를 Task 1~4가 각각
  구현하고, Task 5가 수동 검증한다. 에러 처리(`mlit_unavailable`, 반경
  클램프, 0건=정상)는 Task 4 Step 2·8에서 모두 구현·테스트된다.
- **플레이스홀더 스캔**: 모든 코드 블록이 실행 가능한 완성 코드다. 자체
  리뷰에서 클램프 테스트가 애초엔 호출 인자를 기록하지 않는 더블을 써서
  아무것도 검증하지 못하는(vacuous) 초안이었던 것을 발견해, 호출 인자를
  기록하는 `_RecordingSchoolFacilitySource`로 바로 고쳐 넣었다.
- **타입 일관성**: `SchoolFacility`(Task 1 정의: `facility_id, name, kind,
  lat, lon, distance_m`)가 Task 2(`MlitSchoolFacilitySource.facilities_near`
  반환값 구성)·Task 3(`SchoolFacilities.execute` 반환 타입)·Task 4
  (`act_school_facilities`의 payload dict 키)에서 필드명이 전부 일치한다.
  `SchoolFacilitySource`(Task 1 Protocol: `facilities_near(lat, lon,
  radius_m)`)를 Task 2 의 구현체와 Task 4 의 페이크 더블 모두 정확히 같은
  시그니처로 구현한다. `UseCases`에 `school_facilities` 필드를 추가하면서
  생성 지점 6곳(cli.py 2곳, test_agent_actions.py 4곳)을 전부 짚었다.
- **아키텍처 경계**: domain은 etl을 모른다(`SchoolFacility`를 domain에 새로
  정의, etl의 `Facility`를 재사용하지 않음 — infrastructure 어댑터만 양쪽을
  안다). infrastructure만 MLIT 구체 의존을 알고, application은 포트
  (Protocol)만 안다 — 기존 `hazard_polygons`/`zoning_massing` 배선과 동일한
  패턴.
- **기존 코드 재사용**: `etl/mlit_childcare.py`의 파서·중복제거 로직,
  `etl/mlit_client.py`의 타일 계산·조회 로직을 전부 재사용하고 새로
  베끼지 않았다 — Task 2 는 조합만 새로 한다.
- **프런트엔드**: 이번 계획 범위 밖이다(스펙에 명시). SSE 이벤트 계약은
  이미 확인됐으니, 3D 마커 렌더링은 자연스러운 다음 단계로 남겨둔다.
