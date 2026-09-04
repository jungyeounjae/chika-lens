"""Fake 리포지토리. Phase 1~2에서 BigQuery/MLIT 어댑터로 교체된다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station

#: 가구 유형별 임대료 배수. Phase 1에서 MLIT 실거래 통계로 대체된다.
HOUSEHOLD_RENT_MULTIPLIER: Mapping[Household, float] = {
    Household.SINGLE: 1.0,
    Household.COUPLE: 1.45,
    Household.FAMILY: 1.9,
}


class FakeAreaMetricsRepository:
    def __init__(self, stations: Sequence[Station], raws: Sequence[RawMetrics]) -> None:
        self._stations = list(stations)
        self._raws = list(raws)

    def stations(self) -> Sequence[Station]:
        return self._stations

    def raw_metrics(self) -> Sequence[RawMetrics]:
        return self._raws


class FakeCommuteRepository:
    def __init__(self, table: Mapping[tuple[str, str], int]) -> None:
        self._table = dict(table)

    def minutes_from_all(self, dest_station_id: str) -> Mapping[str, int]:
        minutes = {
            origin: value
            for (origin, dest), value in self._table.items()
            if dest == dest_station_id
        }
        minutes[dest_station_id] = 0
        return minutes


class FakePriceRepository:
    def __init__(self, table: Mapping[str, int]) -> None:
        self._table = dict(table)

    def median_rents(self, household: Household) -> Mapping[str, int]:
        multiplier = HOUSEHOLD_RENT_MULTIPLIER[household]
        return {
            station_id: round(base * multiplier) for station_id, base in self._table.items()
        }
