"""지표 기여도 분해 (스펙 §2.1 '왜 여기가 1위인가').

LLM에 넘길 재료만 만든다. 문장은 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import WARD_RESOLUTION_METRICS, AreaMetrics, MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, PriceRepository
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDetail:
    key: MetricKey
    percentile: float
    contribution: float
    is_missing: bool
    is_ward_resolution: bool


@dataclass(frozen=True)
class AreaExplanation:
    station: Station
    total: float
    rent_yen: int | None
    strengths: list[MetricDetail]
    weaknesses: list[MetricDetail]
    missing: list[MetricKey]


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
            total=area_score.total,
            rent_yen=self._prices.median_rent_yen(station_id, criteria.household),
            strengths=[detail(key) for key, _ in area_score.top_drivers(top_n)],
            weaknesses=[detail(key) for key, _ in area_score.bottom_drivers(top_n)],
            missing=sorted(area.missing),
        )


def _find_area(areas: list[AreaMetrics], station_id: str) -> AreaMetrics:
    for area in areas:
        if area.station_id == station_id:
            return area
    raise KeyError(f"unknown station: {station_id}")
