"""리포지토리 포트. 구현체는 infrastructure 계층에만 존재한다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station


class AreaMetricsRepository(Protocol):
    def stations(self) -> Sequence[Station]: ...

    def raw_metrics(self) -> Sequence[RawMetrics]: ...


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
