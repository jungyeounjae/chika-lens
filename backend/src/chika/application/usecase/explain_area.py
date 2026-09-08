"""지표 기여도 분해 (스펙 §2.1 '왜 여기가 1위인가').

LLM에 넘길 재료만 만든다. 문장은 만들지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import WARD_RESOLUTION_METRICS, AreaMetrics, MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, PriceRepository
from chika.domain.service.dials import expand_dials
from chika.domain.service.geo import distance_meters
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDetail:
    key: MetricKey
    percentile: float
    contribution: float
    is_missing: bool
    is_ward_resolution: bool


#: 주변 역 탐색 반경. 도보권(800m)을 넘지만 "다른 선택지"로 볼 만한 거리다.
NEARBY_RADIUS_M = 1_500.0

#: 지도가 읽히는 한계. 신주쿠 일대는 이 반경에 역이 수십 개 있다.
MAX_NEARBY = 8


@dataclass(frozen=True)
class NearbyStation:
    station: Station
    distance_m: float


@dataclass(frozen=True)
class AreaExplanation:
    station: Station
    total: float
    rent_yen: int | None
    strengths: list[MetricDetail]
    weaknesses: list[MetricDetail]
    missing: list[MetricKey]
    #: 주변 역. 좌표가 이미 로컬에 있어 API 호출이 필요 없다 —
    #: 역이 하나뿐인 동네와 여러 노선이 겹치는 동네의 차이를 지도에서 보여준다.
    nearby: list[NearbyStation]


class ExplainArea:
    def __init__(self, areas: AreaMetricsRepository, prices: PriceRepository) -> None:
        self._areas = areas
        self._prices = prices

    def execute(
        self, station_id: str, criteria: SearchCriteria, top_n: int = 3
    ) -> AreaExplanation:
        station = next((s for s in self._areas.stations() if s.id == station_id), None)
        if station is None:
            raise KeyError(f"unknown station: {station_id}")

        area = _find_area(normalize(self._areas.raw_metrics()), station_id)
        area_score = score(area, expand_dials(criteria.dials))

        def detail(key: MetricKey) -> MetricDetail:
            return MetricDetail(
                key=key,
                percentile=area.percentile[key],
                contribution=area_score.contributions[key],
                is_missing=key in area.missing,
                is_ward_resolution=key in WARD_RESOLUTION_METRICS,
            )

        return AreaExplanation(
            station=station,
            nearby=_nearby(station, self._areas.stations()),
            total=area_score.total,
            rent_yen=self._prices.median_rents(criteria.household).get(station_id),
            strengths=[detail(key) for key, _ in area_score.top_drivers(top_n)],
            weaknesses=[detail(key) for key, _ in area_score.bottom_drivers(top_n)],
            missing=sorted(area.missing),
        )


def _nearby(origin: Station, stations: Sequence[Station]) -> list[NearbyStation]:
    """반경 안의 다른 역을 가까운 순으로. 자기 자신은 뺀다."""
    found = [
        NearbyStation(
            station=other,
            distance_m=distance_meters(origin.lat, origin.lon, other.lat, other.lon),
        )
        for other in stations
        if other.id != origin.id
    ]
    within = [n for n in found if n.distance_m <= NEARBY_RADIUS_M]
    within.sort(key=lambda n: (n.distance_m, n.station.id))
    return within[:MAX_NEARBY]


def _find_area(areas: list[AreaMetrics], station_id: str) -> AreaMetrics:
    for area in areas:
        if area.station_id == station_id:
            return area
    raise KeyError(f"unknown station: {station_id}")
