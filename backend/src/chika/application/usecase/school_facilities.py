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
