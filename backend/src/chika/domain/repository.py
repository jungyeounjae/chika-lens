"""리포지토리 포트. 구현체는 infrastructure 계층에만 존재한다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station


class AreaMetricsRepository(Protocol):
    def stations(self) -> Sequence[Station]: ...

    def raw_metrics(self) -> Sequence[RawMetrics]: ...


class CommuteRepository(Protocol):
    def minutes_to(self, origin_station_id: str, dest_station_id: str) -> int | None:
        """알 수 없으면 None. 하드 필터는 None을 '탈락'이 아니라 '판단 보류'로 다룬다."""
        ...


class PriceRepository(Protocol):
    def median_rent_yen(self, station_id: str, household: Household) -> int | None: ...
