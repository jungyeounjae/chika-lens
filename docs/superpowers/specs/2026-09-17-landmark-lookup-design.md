# 랜드마크 이름 → 좌표 변환 — 설계

**목표:** "신주쿠교엔 근처 살기 좋아?"처럼 역이 아닌 지명(공원·랜드마크·
관광지)으로 물어도, 좌표를 찾아 가장 가까운 역으로 이어서 기존 분석 전체
(`explain_area`/`hazard_polygons`/`zoning_massing`/`school_facilities`/
`park_polygons`)를 그대로 쓸 수 있게 한다.

**배경:** 현재 `lookup_station`은 489역 이름의 부분일치만 본다 — 역이 아닌
지명은 애초에 대상이 아니다. 실측(2026-09-17)으로 두 후보를 비교했다:

- `backend/src/chika/etl/gsi_geocoder.py`(国土地理院 주소검색, 이미 신축
  물건 배치에서 사용 중)로 "新宿御苑"을 검색하면 전국의 "新宿"이 들어간
  무관한 지명들만 나오고 정작 신주쿠교엔은 안 나온다 — 이 API는 **주소**
  검색이지 랜드마크/POI 이름 검색이 아니다.
- Nominatim(OpenStreetMap)으로 같은 질의를 하면 정확히
  `新宿御苑`(lat 35.6851, lon 139.7095)을 1위로 반환한다. `park_polygons`가
  이미 같은 OSM 생태계(Overpass)를 쓰고 있어 라이선스·출처 표기 패턴도
  그대로 재사용된다.

→ 지오코딩 백엔드로 **Nominatim**을 채택한다. GSI 지오코더는 그대로 두고
(신축 물건 주소 배치용 역할은 변하지 않는다) 건드리지 않는다.

## 기존 자산 재사용

- `domain/service/geo.py`의 `distance_meters(lat1, lon1, lat2, lon2)` —
  `explain_area`의 `_nearby()`가 이미 쓰는 하버사인 함수. 가장 가까운 역
  계산에 새 거리 코드가 필요 없다.
- `domain/repository.py`의 `HazardPolygonSource`/`ZoningPolygonSource`/
  `ParkPolygonSource` — 같은 자리에 `LandmarkGeocoder` 포트를 추가한다.
- `etl/overpass_client.py`(raw HTTP 클라이언트) +
  `infrastructure/overpass_park_source.py`(포트 구현체, 클라이언트를 감싸
  도메인 값 객체로 변환) — 스로틀(`_MIN_INTERVAL_SECONDS`)·재시도
  (`_MAX_ATTEMPTS`, `_RETRY_STATUS`)·transport 주입 패턴과 두 파일 분리
  방식 모두의 정확한 선례. Nominatim도 같은 2단 구조로 만든다.
- `interface/agent/actions.py`의 `act_lookup_station`(231번째 줄) — 이름
  검색 결과를 `matches` 배열로 돌려주는 정확한 선례. `act_hazard_polygons`의
  반경 클램프 + 에러 dict 패턴도 그대로 따른다.
- `application/usecase/hazard_polygons.py`의 `HazardPolygons` — 포트를 받아
  `AreaMetricsRepository`와 조합하는 usecase 클래스의 정확한 선례.
  `LookupLandmark`도 이 모양을 따른다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint, `mypy --strict`(`uv run mypy src`) 통과.
- domain 계층은 `infrastructure`/`etl`를 몰라야 한다.
- **호출 예절**: Nominatim 공식 사용 정책 — 초당 1회 이하, 식별 가능한
  User-Agent 필수. `overpass_client.py`와 동일하게
  `_MIN_INTERVAL_SECONDS = 1.0`, `_MAX_ATTEMPTS = 3`,
  `_RETRY_STATUS = {429, 500, 502, 503, 504}`을 적용한다.
- **라이선스**: OSM 데이터는 ODbL — `park_polygons`와 같은
  `attribution: "© OpenStreetMap contributors"`를 결과에 담는다.
- **검색 범위**: `countrycodes=jp`로 일본 내로만 제한한다. 도쿄 바운딩박스로
  더 좁히지 않는다 — 23구 경계 인접 지역의 정당한 매치를 놓칠 수 있어서다.
  대신 아래 거리 상한으로 엉뚱한 매치를 걸러낸다.
- **거리 상한**: 가장 가까운 역까지 2,000m 초과 시 `far_from_any_station:
  true`를 반환값에 담는다. 에이전트는 이 플래그를 보면 반드시 "이 역 기준
  데이터가 실제 지점과 거리가 있다"고 답변에 명시해야 한다 — 조용히 먼 역
  데이터를 그 지점 것처럼 말하지 않는다.
- **매칭 개수**: 상위 최대 3개 후보를 반환한다(`lookup_station`의 `matches`
  패턴과 동일). 0건이면 `{"matches": []}`.
- **에러 처리**: 네트워크 실패는 다른 실시간 툴과 같은 모양
  `{"error": "geocoder_unavailable", "detail": str(exc)}`로 반환한다 —
  대화 전체를 죽이지 않는다.

## 컴포넌트

### 1. `domain/model/landmark.py` (신규) — `LandmarkMatch` 값 객체

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

### 2. `domain/repository.py` 수정 — `LandmarkGeocoder` 포트 추가

`from chika.domain.model.landmark import LandmarkMatch` import를 추가하고
파일 끝에:

```python
class LandmarkGeocoder(Protocol):
    """랜드마크/POI 이름 → 좌표 지오코딩 포트. 구현체(infrastructure)가
    외부 API 호출·재시도를 끝낸 결과만 돌려준다."""

    def search(self, query: str, limit: int) -> Sequence[LandmarkMatch]: ...
```

### 3. `etl/nominatim_client.py` (신규) — raw HTTP 클라이언트

`overpass_client.py`와 완전히 같은 transport 주입·스로틀·재시도 골격
(`GET https://nominatim.openstreetmap.org/search?q=<query>&format=json&limit=<limit>&countrycodes=jp`).
`NominatimClient.search(query, limit) -> list[dict]`(파싱 전 raw JSON 배열)과
`NominatimFetchError`(`OverpassFetchError`와 같은 모양)를 제공한다.

### 4. `infrastructure/nominatim_geocoder.py` (신규) — `NominatimGeocoder`

`infrastructure/overpass_park_source.py`와 같은 역할 — `NominatimClient`를
감싸 `LandmarkGeocoder` 포트를 구현하고, raw JSON을 도메인 값 객체로
변환한다. 응답 배열의 각 원소에서 `name`(없으면 `display_name`의 첫
구성요소), `lat`/`lon`(문자열로 옴 — `float()` 변환)을 뽑아
`LandmarkMatch` 리스트로 만든다.

### 5. `application/usecase/lookup_landmark.py` (신규) — `LookupLandmark`

```python
"""랜드마크 이름 → 좌표 → 가장 가까운 역. 3D/좌표 기반 툴 및 station_id
기반 분석 전체(explain_area 등)의 입구를 역이 아닌 지명에도 열어준다."""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.landmark import LandmarkMatch
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, LandmarkGeocoder
from chika.domain.service.geo import distance_meters

#: 가장 가까운 역도 이보다 멀면 "이 역 데이터가 실제 지점과 거리가 있다"고
#: 경고한다 — 조용히 먼 역 데이터를 그 지점 것처럼 말하는 걸 막는다.
FAR_FROM_STATION_M = 2_000.0

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

(`Sequence`는 `collections.abc`에서 import — 다른 파일과 동일한 관례.)

### 6. `interface/agent/state.py` 수정 — `UseCases`에 필드 추가

```python
    #: 랜드마크 이름 → 좌표 → 가장 가까운 역. lookup_station이 못 찾을 때
    #: 이어서 쓴다(landmark_lookup.py 참고).
    lookup_landmark: LookupLandmark
```

### 7. `interface/agent/actions.py` 수정 — `act_lookup_landmark` 추가

`act_hazard_polygons`(617번째 줄 근처)와 같은 자리에. `act_hazard_polygons`가
`from chika.etl.mlit_client import MlitApiError`를 이미 이런 식으로 import해
쓰는 선례를 그대로 따라 `from chika.etl.nominatim_client import
NominatimFetchError`를 파일 상단 import 블록에 추가한다:

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

### 8. `interface/agent/tools.py` 수정 — `lookup_landmark` 툴 추가

`lookup_station` 바로 다음에:

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

### 9. `interface/agent/prompts.py` 수정 — 규칙 추가

`lookup_station`을 설명하는 기존 문장 근처에 규칙을 추가한다: "역 이름으로
못 찾겠으면(사용자가 공원·랜드마크·관광지 등 역이 아닌 지명을 말한 경우)
`lookup_landmark`를 이어서 시도합니다. 후보가 여럿이면 문맥상 가장 그럴듯한
것을 고르거나 사용자에게 확인합니다. `far_from_any_station`이 true인 후보를
쓸 때는 반드시 '가장 가까운 역이 실제로는 좀 떨어져 있다'는 사실을
답변에서 밝힙니다."

### 10. 합성 루트(`cli.py` 등) 수정

`build_real_session`/`build_demo_session`에서 다른 usecase들과 같은 자리에
`LookupLandmark(areas, NominatimGeocoder())`를 조립해 `UseCases`에 넘긴다
(데모 세션은 페이크 geocoder를 쓴다 — 다른 usecase들과 동일 패턴).

## 테스트

- `tests/domain/model/test_landmark.py` — 값 객체 생성만(다른 값 객체와
  동일하게 간단).
- `tests/etl/test_nominatim_client.py` — `tests/etl/test_overpass_client.py`와
  같은 모양: 페이크 transport로 JSON 응답 주입, 스로틀·재시도·HTTP 에러 케이스.
- `tests/infrastructure/test_nominatim_geocoder.py` —
  `tests/infrastructure/test_overpass_park_source.py`와 같은 모양: 페이크
  `NominatimClient`로 raw JSON → `LandmarkMatch` 파싱(이름 결측 시
  `display_name` 폴백 포함)을 검증.
- `tests/application/test_lookup_landmark.py` — 페이크 geocoder + 페이크
  `AreaMetricsRepository`로: (a) 가장 가까운 역이 정확히 계산되는지, (b)
  2,000m 초과 시 `far_from_any_station=True`, (c) 매칭 0건일 때 빈 리스트.
- `tests/interface/test_agent_actions.py` — `act_lookup_landmark` 추가:
  정상 케이스, 빈 질의, `geocoder_unavailable` 에러 케이스.

## 프런트엔드

변경 없음 — `lookup_landmark`가 찾아준 `station_id`로 이후 흐름
(`explain_area` 등)이 그대로 타므로 기존 지도/오버레이 렌더링을 그대로
재사용한다.
