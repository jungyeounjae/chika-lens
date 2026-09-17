"""리포지토리 포트. 구현체는 infrastructure 계층에만 존재한다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from chika.domain.model.criteria import Household
from chika.domain.model.facility import SchoolFacility
from chika.domain.model.landmark import LandmarkMatch
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.new_construction import NewConstructionListing
from chika.domain.model.polygon import HazardPolygon, ParkPolygon, ZoningPolygon
from chika.domain.model.station import Station


class AreaMetricsRepository(Protocol):
    def stations(self) -> Sequence[Station]: ...

    def raw_metrics(self) -> Sequence[RawMetrics]: ...


class HazardPolygonSource(Protocol):
    """3D 시각화용 원본 재해 Polygon 조회 포트. 구현체가 거리 필터링·심각도
    변환(shapely 등 외부 의존)을 끝내고 이미 걸러진 결과만 돌려준다."""

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[HazardPolygon]: ...


class ZoningPolygonSource(Protocol):
    """3D 시각화용 원본 용도지역 Polygon 조회 포트. 위와 같은 이유로 구현체가
    필터링을 끝낸 결과만 돌려준다."""

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[ZoningPolygon]: ...


class CommuteRepository(Protocol):
    def minutes_from_all(self, dest_station_id: str) -> Mapping[str, int]:
        """목적지까지의 소요시간을 역 id → 분으로 한 번에 반환한다.

        역마다 조회하면 실제 어댑터에서 역 수만큼 라운드트립이 된다.
        키의 부재가 '알 수 없음'이며, 하드 필터는 이를 '탈락'이 아니라
        '판단 보류'로 다룬다.
        """
        ...


class PriceRepository(Protocol):
    def median_rents(self, household: Household) -> Mapping[str, int]:
        """가구 유형에 대한 역 id → 시세 중앙값을 한 번에 반환한다.

        키의 부재가 '시세를 모른다'는 뜻이다. 위와 같은 이유로 배치 조회다.
        """
        ...


class NewConstructionRepository(Protocol):
    """신축 분양 물건 조회 포트. 실시간 크롤링이 아니라 배치 산출물을 읽는다."""

    def listings(self) -> Sequence[NewConstructionListing]: ...


class SchoolFacilitySource(Protocol):
    """학교/보육시설 3D 시각화 포트. 요청 단위 실시간 조회 — 배치가 아니다."""

    def facilities_near(
        self, lat: float, lon: float, radius_m: float
    ) -> Sequence[SchoolFacility]: ...


class ParkPolygonSource(Protocol):
    """3D 시각화용 OSM 공원 Polygon 조회 포트. 구현체(infrastructure)가
    Overpass 응답을 이미 GeoJSON으로 변환한 결과만 돌려준다."""

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[ParkPolygon]: ...


class LandmarkGeocoder(Protocol):
    """랜드마크/POI 이름 → 좌표 지오코딩 포트. 구현체(infrastructure)가
    외부 API 호출·재시도를 끝낸 결과만 돌려준다."""

    def search(self, query: str, limit: int) -> Sequence[LandmarkMatch]: ...
