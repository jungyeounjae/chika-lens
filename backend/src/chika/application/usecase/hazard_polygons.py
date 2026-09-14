"""역 하나 주변의 재해위험 원본 Polygon(홍수·토사재해) — 3D 시각화용.

`metric_distribution`이 쓰는 정규화 percentile과 달리, 여기는 MLIT 원본
구역 경계를 그대로 낸다 — PDL1.0이 출처 표기 조건으로 허용한다(스펙
§3.1.2 정정, 2026-09-11). 실제 조회(타일 계산·거리 필터링·심각도 변환)는
`HazardPolygonSource` 포트의 구현체(infrastructure)가 맡는다 — 이 유스케이스는
역 좌표를 찾아 포트에 넘기고 결과를 그대로 돌려줄 뿐이다.
"""

from __future__ import annotations

from chika.domain.model.polygon import HazardPolygon
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, HazardPolygonSource

RADIUS_M = 800.0


class HazardPolygons:
    def __init__(self, areas: AreaMetricsRepository, source: HazardPolygonSource) -> None:
        self._areas = areas
        self._source = source

    def execute(
        self, station_id: str, radius_m: float = RADIUS_M
    ) -> tuple[Station, list[HazardPolygon]]:
        station = next((s for s in self._areas.stations() if s.id == station_id), None)
        if station is None:
            raise KeyError(f"unknown station: {station_id}")
        polygons = list(self._source.polygons_near(station.lat, station.lon, radius_m))
        return station, polygons
