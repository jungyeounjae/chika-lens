"""역 하나 주변의 용도지역 원본 Polygon — 3D 도시 밀도(매싱) 시각화용.

`hazard_polygons.py`와 같은 구조다 — 타일 계산·거리 필터링·높이 매핑은
`ZoningPolygonSource` 포트 구현체(infrastructure)가 맡는다.
"""

from __future__ import annotations

from chika.domain.model.polygon import ZoningPolygon
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, ZoningPolygonSource

RADIUS_M = 500.0


class ZoningMassing:
    def __init__(self, areas: AreaMetricsRepository, source: ZoningPolygonSource) -> None:
        self._areas = areas
        self._source = source

    def execute(
        self, station_id: str, radius_m: float = RADIUS_M
    ) -> tuple[Station, list[ZoningPolygon]]:
        station = next((s for s in self._areas.stations() if s.id == station_id), None)
        if station is None:
            raise KeyError(f"unknown station: {station_id}")
        polygons = list(self._source.polygons_near(station.lat, station.lon, radius_m))
        return station, polygons
