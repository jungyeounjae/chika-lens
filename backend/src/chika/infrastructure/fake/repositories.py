"""Fake 리포지토리 — `domain.repository`의 포트 3개를 인메모리로 구현한다.

`FakeAreaMetricsRepository`는 테스트·데모 전용이다. 실운영 지표는
`FileAreaMetricsRepository`가 배치 산출 JSON을 읽어 채운다.

`FakeCommuteRepository`·`FakePriceRepository`는 소스가 아예 없는 두 값
(역간 소요시간, 월세)의 자리를 채운다 — 테스트뿐 아니라
`cli.build_real_session`의 실데이터 세션에서도 빈 채로 그대로 쓰인다. 키가
없으면 하드 필터가 '탈락'이 아니라 '판단 보류'로 다루고, 화면에는 '데이터
없음'으로 나간다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station

#: 가구 유형별 임대료 배수 — 임대 시세 소스가 없을 때 쓰는 근사치다.
#: MLIT 거래가격(지표 13)은 매매 단가만 주고 임대(월세) 데이터가 없어
#: 이 배수를 대체하지 못한다. 실측으로 바꾸려면 별도의 임대 시세 소스가 있어야 한다.
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
