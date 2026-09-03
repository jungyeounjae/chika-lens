"""후보지 비교 (스펙 §2.2-1). 차이 나는 축만 위로 올린다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDifference:
    key: MetricKey
    percentiles: dict[str, float]
    spread: float


@dataclass(frozen=True)
class AreaComparison:
    stations: list[Station]
    totals: dict[str, float]
    differences: list[MetricDifference]


class CompareAreas:
    def __init__(self, areas: AreaMetricsRepository) -> None:
        self._areas = areas

    def execute(
        self,
        station_ids: Sequence[str],
        criteria: SearchCriteria,
        top_n: int = 5,
    ) -> AreaComparison:
        if len(station_ids) < 2:
            raise ValueError("compare needs at least two stations")

        by_id = {station.id: station for station in self._areas.stations()}
        stations = []
        for station_id in station_ids:
            if station_id not in by_id:
                raise KeyError(f"unknown station: {station_id}")
            stations.append(by_id[station_id])

        areas = {area.station_id: area for area in normalize(self._areas.raw_metrics())}
        weights = expand_dials(criteria.dials)

        totals = {sid: score(areas[sid], weights).total for sid in station_ids}

        differences = []
        for key in MetricKey:
            percentiles = {sid: areas[sid].percentile[key] for sid in station_ids}
            values = list(percentiles.values())
            differences.append(
                MetricDifference(
                    key=key,
                    percentiles=percentiles,
                    spread=max(values) - min(values),
                )
            )
        differences.sort(key=lambda diff: (-diff.spread, diff.key.value))

        return AreaComparison(
            stations=stations,
            totals=totals,
            differences=differences[:top_n],
        )
