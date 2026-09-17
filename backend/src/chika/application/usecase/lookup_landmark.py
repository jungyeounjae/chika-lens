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
