# 학교/보육시설 3D 시각화용 실시간 조회 — 설계

**목표:** "이 동네 아이 키우기 좋아?", "살기 좋은 곳이야?" 같은 질문에 챗봇이
학교·보육시설 위치를 좌표로 돌려줘서, 프런트엔드가 3D로 마커를 찍어 보여줄
수 있게 한다. 배치로 신축 물건에 필드를 채우는 게 아니라 — `hazard_polygons`/
`zoning_massing`과 같은 **요청 단위 실시간 조회** 패턴이다.

**배경:** 사용자가 애초에 제안한 "신축 물건 주변 생활 인프라 3D 시각화"(공원·
학교·대형상업시설)를 학교/보육시설부터 순서대로 착수하기로 했다(2026-09-14
대화). 원래는 신축 물건 배치 보강(`build_new_construction_enrichment.py`에
필드 추가)으로 잡았으나, 실제 목표는 "3D로 뭐든 보여주고 싶다"는 것이라 —
역(rank_areas)이든 신축 물건(search_new_construction)이든 좌표만 있으면
동작해야 한다는 게 확인되어 좌표(lat/lon) 기반 실시간 조회로 방향을 잡았다.

## 기존 자산 재사용

`etl/mlit_childcare.py`에 이미 있는 것을 그대로 쓴다 — 새로 만들 필요 없음:

- `Facility(facility_id, lat, lon, kind, name)` — etl 내부 파싱 결과 값 객체.
- `parse_preschool(feature) -> Facility | None` — XKT007(幼稚園・保育所), 폐원 제외.
- `parse_school(feature) -> Facility | None` — XKT006(学校), `SCHOOL_KINDS_COUNTED`
  (초등학교·중학교·義務教育学校만, 고교/대학 제외 — 기존 지표 11과 같은 curation).
- `deduplicate(facilities) -> list[Facility]` — 타일 경계 중복 제거.
- `etl/mlit_client.py`의 `tiles_covering(points, zoom, margin_m)` — 좌표 주변
  타일 계산. `margin_m`에 조회 반경을 그대로 넘기면 된다
  (`mlit_hazard_source.py`가 이미 이렇게 쓴다: `tiles_covering([(lat, lon)],
  dataset.zoom, radius_m)`).
- `domain/service/geo.py`의 `distance_meters(lat1, lon1, lat2, lon2) -> float`.

이 모듈들은 이미 테스트가 있다 — 재검증하지 않는다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과, `mypy --strict` 통과(프로젝트 컨벤션: `uv run mypy src`).
- domain 계층은 `etl`/`infrastructure`를 몰라야 한다 — `etl.mlit_childcare.Facility`를
  domain에서 재사용하지 않는다. `domain/model/facility.py`에 별도 `SchoolFacility`
  값 객체를 새로 정의하고, infrastructure 어댑터가 etl의 `Facility`를 이 타입으로
  변환한다.
- `UseCases`(`interface/agent/state.py`)는 `frozen=True` dataclass라 필드
  하나를 추가하면 **모든 생성 지점**을 고쳐야 한다 — 2026-09-14 기준 정확히
  6곳: `backend/src/chika/interface/cli.py:65`(`build_demo_session`),
  `cli.py:124`(`build_real_session`), `backend/tests/interface/test_agent_actions.py:120`,
  `:141`, `:1026`, `:1132`. 하나라도 빠뜨리면 그 파일의 다른 테스트가
  `TypeError: missing argument`로 전부 깨진다. **구현 시작 전에 반드시
  `grep -n "UseCases(" backend/src/chika/interface/cli.py backend/tests/interface/test_agent_actions.py`로
  재확인** — 이 세션 안에서도 이미 5→6으로 늘어난 적이 있다(테스트 헬퍼 추가로).
- 기존 `hazard_polygons`/`zoning_massing`과 이름·구조 스타일을 맞춘다(포트는
  `XxxSource` + `_near` 메서드, usecase는 반경 기본값 상수, action은 에러를
  `{"error": ...}` dict로 반환하지 예외를 올리지 않음).
- 반경 상한을 반드시 클램프한다(`hazard_polygons`의 `_MAX_POLYGON_RADIUS_M`과
  같은 이유 — 사용자가 반경을 비정상적으로 크게 주면 타일 요청이 폭증한다).
- 결과 0건은 에러가 아니다("이 반경 안에 학교 없음"은 정상 응답).

## 컴포넌트

### 1. `domain/model/facility.py` (신규)

```python
"""3D 시각화용 시설 값 객체 — etl 배치 산출물이 아니라 요청 단위 실시간 조회 결과.

etl.mlit_childcare.Facility 와 필드가 겹치지만 별개 타입이다 — domain 은 etl 을
몰라야 한다(Clean Architecture). infrastructure 어댑터가 변환한다.
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
    #: 조회 좌표로부터의 거리(m). 조회 시점에만 의미가 있어 도메인 엔티티
    #: 고유값은 아니지만, NewConstructionQuietness.distance_m 과 같은 선례로
    #: 값 객체 안에 포함시킨다 — 정렬·표시에 바로 쓸 수 있게.
    distance_m: float
```

### 2. `domain/repository.py` 수정

임포트 블록에 추가(알파벳 순, 기존 `from chika.domain.model.criteria import ...`
근처 — 기존 import 정렬 규칙을 따른다):

```python
from chika.domain.model.facility import SchoolFacility
```

파일 끝에 Protocol 추가:

```python
class SchoolFacilitySource(Protocol):
    """학교/보육시설 3D 시각화 포트. 요청 단위 실시간 조회 — 배치가 아니다."""

    def facilities_near(self, lat: float, lon: float, radius_m: float) -> Sequence[SchoolFacility]: ...
```

### 3. `infrastructure/mlit_school_source.py` (신규)

```python
"""`SchoolFacilitySource` 포트의 실제 구현 — MLIT 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와 같은
구조 — 배치가 아니라 요청 한 건을 위해 MLIT 을 실시간으로 호출한다(호출
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

**주의:** `PRESCHOOL.facility_id`가 빈 문자열일 수 있다(`mlit_childcare.py`의
`deduplicate`가 `facility_id`가 빈 값이면 중복 제거를 건너뛴다 — 원본 그대로의
동작이다, 여기서 새로 만드는 문제가 아니다).

### 4. `application/usecase/school_facilities.py` (신규)

```python
"""학교/보육시설 실시간 조회 — 3D 시각화 재료. hazard_polygons.py 와 같은 구조.

station_id 가 아니라 좌표를 직접 받는다 — 역(rank_areas)이든 신축 물건
(search_new_construction)이든 lat/lon 만 있으면 동작해야 하기 때문이다
(2026-09-14 설계 논의).
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

### 5. 에이전트 배선 (기존 hazard_polygons 4단 배선과 동일한 패턴)

**`interface/agent/state.py`:**
- `UseCases`에 필드 추가: `school_facilities: SchoolFacilities` (import
  `from chika.application.usecase.school_facilities import SchoolFacilities`).
  `hazard_polygons`/`zoning_massing` 필드 바로 뒤에 둔다(같은 "실시간 조회"
  묶음이라는 주석과 함께).

**`interface/agent/actions.py`:**

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

(`MlitApiError`는 이미 actions.py 상단에서 import 돼 있다 — 재사용.)

**`interface/agent/tools.py`:**

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
    한국어로 지어내 번역하지 않는다.
    """
    return actions.act_school_facilities(ctx.context, lat=lat, lon=lon, radius_m=radius_m)
```

**`interface/agent/agents.py`:** import 블록에 `school_facilities` 알파벳 순
추가, `AnalysisAgent.tools` 리스트 끝에 추가.

**`interface/agent/prompts.py`:** `ANALYSIS_INSTRUCTIONS`에 새 bullet 추가
(`zoning_massing` 안내 문단 뒤, `search_new_construction` 안내 문단 앞 —
정확한 삽입 지점은 구현 시점에 `grep -n` 으로 재확인):

```
- **"아이 키우기 좋아?", "학교 가까워?" 같은 교육 인프라 질문은
  school_facilities.** `lat`/`lon`은 방금 조회한 역이나 신축 물건의 좌표를
  그대로 쓴다. 결과 0건은 "이 반경 안에 학교 없음"이지 오류가 아니다 —
  그렇게 답한다. `kind`는 원문(일본어) 그대로 나오니 자연스럽게 풀어서
  설명한다(예: "小学校" → "초등학교").
```

**`interface/cli.py`:** `_mlit_client()`를 그대로 재사용(이미 존재).
`build_demo_session`/`build_real_session` 둘 다 `UseCases(...)`에 추가:

```python
school_facilities=SchoolFacilities(MlitSchoolFacilitySource(client)),
```

(기존 `hazard_polygons=HazardPolygons(areas, MlitHazardPolygonSource(client))`
바로 뒤에 둔다 — `client`는 이미 함수 안에서 만들어져 있다.)

## 에러 처리 / 결측 의미론

- MLIT 호출 실패(`MlitApiError`) → `{"error": "mlit_unavailable", "detail": ...}`.
- 반경이 상한을 넘으면 조용히 클램프한다(에러 아님) — `hazard_polygons`와 동일.
- 결과 0건은 정상("이 반경 안에 학교 없음") — 에러 dict 를 돌려주지 않는다.
- `kind`가 빈 문자열일 일은 없다 — `parse_preschool`/`parse_school`이 이미
  빈 kind 를 만들지 않게 보장한다(mlit_childcare.py 기존 로직).

## 테스트

- `tests/infrastructure/test_mlit_school_source.py` (신규) — `test_mlit_hazard_source.py`와
  같은 transport 주입 패턴. 확인할 것: 반경 안 시설만 포함, 반경 밖 제외,
  타일 중복 제거, preschool+school 합쳐서 거리순 정렬.
- `tests/application/test_school_facilities.py` (신규) — fake source 로
  `execute()`가 그대로 위임하는지만 확인(로직이 없으므로 최소 테스트).
- `tests/interface/test_agent_actions.py`에 `act_school_facilities` 테스트
  추가 + 기존 6곳의 `UseCases(...)`에 `school_facilities=` 필드 추가(누락 시
  그 파일 테스트 전부 `TypeError`로 깨짐 — Global Constraints 참고).
- `tests/interface/test_agent_wiring.py`의 `AnalysisAgent` 정확 툴셋 단언에
  `"school_facilities"` 추가.
- 전체 스위트 + `ruff check .` + `uv run mypy src` 통과 확인.
- 수동 검증(Task 5 스타일): `build_real_session()` + `act_school_facilities`를
  신주쿠 실좌표로 직접 호출해 실제 학교가 나오는지 확인.

## 이번 범위 밖

- 공원(park), 대형상업시설(P31, 정확한 데이터셋 아직 미확인) — 각각 별도 설계.
  이 설계의 포트(`SchoolFacilitySource`)를 그대로 재사용하지 않는다 —
  `hazard_polygons`/`zoning_massing`이 각자 별도 포트인 것과 같은 이유로,
  공원/상업시설도 각자의 포트를 새로 정의한다(데이터 소스 모양이 다르므로).
- 프런트엔드 3D 마커 렌더링(Three.js 레이어) — 백엔드 툴 배선까지만. SSE
  이벤트 계약(`{tool, result}`)은 이미 확인됐으니 자연스러운 다음 단계.
- 신축 물건 배치 보강(`build_new_construction_enrichment.py`에 필드 추가) —
  이 설계는 실시간 조회로 방향을 바꿨으므로 해당 없음.
