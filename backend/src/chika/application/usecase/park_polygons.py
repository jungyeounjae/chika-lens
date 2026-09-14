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
