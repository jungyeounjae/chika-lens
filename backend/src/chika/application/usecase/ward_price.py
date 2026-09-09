"""구 단위 시세 요약 — "땅값이 가장 낮은/높은 구는 어디야?"에 답한다.

**이 데이터는 공시지가(地価公示)가 아니다.** 政府가 매년 고시하는 평가액과
달리, `price_level`(지표 13)은 MLIT 부동산 거래가격 정보의 **실거래
사례 중앙값**이다 — 다른 지표라서 답변에서 반드시 구분해야 한다.

역 단위 값을 구 단위로 묶으면 해상도가 낮아진다는 트레이드오프가 있다.
그래서 "대표 역"을 함께 낸다 — 구 전체의 숫자 하나보다, 그 구 안에서
실제로 중앙값에 가까운 역이 어디인지가 사용자에게 더 검증 가능하다.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from chika.domain.model.metrics import AreaMetrics, MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository
from chika.domain.service.normalization import normalize

#: 구 하나에서 대표로 뽑는 역의 수. 하나만 내면 "왜 하필 이 역이냐"는
#: 우연으로 보이고, 셋 이상은 화면이 붐빈다.
REPRESENTATIVE_COUNT = 2


@dataclass(frozen=True)
class RepresentativeStation:
    station: Station
    price_level: float
    price_percentile: float
    #: 상업 밀도의 대리 지표. "저평가된 이유"를 지어내지 않고 이 값으로만
    #: 말하게 하려고 함께 낸다 — "도심 거리"는 애초에 지표에 없다.
    supermarket_percentile: float
    convenience_store_percentile: float


@dataclass(frozen=True)
class WardPrice:
    ward: str
    median_price: float
    #: 이 구에서 price_level 이 결측이 아닌 역의 수. 표본이 적으면 중앙값의
    #: 신뢰도가 떨어진다는 걸 사용자가 판단할 수 있어야 한다.
    station_count: int
    representative: list[RepresentativeStation]


class WardPriceRanking:
    def __init__(self, areas: AreaMetricsRepository) -> None:
        self._areas = areas

    def execute(self) -> list[WardPrice]:
        """구 목록을 시세 오름차순으로. 빈 리스트는 price_level 이 통째로
        결측이라는 뜻이다(배치를 아직 안 돌렸거나 실패한 경우)."""
        stations = list(self._areas.stations())
        raws = self._areas.raw_metrics()
        raw_by_id = {r.station_id: r for r in raws}
        area_by_id = {a.station_id: a for a in normalize(raws)}

        by_ward: dict[str, list[Station]] = defaultdict(list)
        for station in stations:
            raw = raw_by_id.get(station.id)
            if raw is not None and raw.get(MetricKey.PRICE_LEVEL) is not None:
                by_ward[station.ward].append(station)

        wards = [
            self._summarise(ward, members, raw_by_id, area_by_id)
            for ward, members in by_ward.items()
        ]
        wards.sort(key=lambda w: w.median_price)
        return wards

    @staticmethod
    def _summarise(
        ward: str,
        members: list[Station],
        raw_by_id: dict[str, RawMetrics],
        area_by_id: dict[str, AreaMetrics],
    ) -> WardPrice:
        priced: list[tuple[Station, float]] = []
        for station in members:
            price = raw_by_id[station.id].get(MetricKey.PRICE_LEVEL)
            assert price is not None  # by_ward 를 채울 때 이미 걸러졌다
            priced.append((station, price))
        median = statistics.median(price for _, price in priced)

        # 중앙값에 가장 가까운 역이 그 구의 "전형적인" 가격대를 보여준다 —
        # 최고가·최저가 역을 뽑으면 그 구 안의 극단값이지 대표값이 아니다.
        priced.sort(key=lambda item: abs(item[1] - median))

        def detail(station: Station, price: float) -> RepresentativeStation:
            area = area_by_id[station.id]
            return RepresentativeStation(
                station=station,
                price_level=price,
                price_percentile=area.percentile[MetricKey.PRICE_LEVEL],
                supermarket_percentile=area.percentile[MetricKey.SUPERMARKET],
                convenience_store_percentile=area.percentile[MetricKey.CONVENIENCE_STORE],
            )

        return WardPrice(
            ward=ward,
            median_price=median,
            station_count=len(members),
            representative=[
                detail(station, price) for station, price in priced[:REPRESENTATIVE_COUNT]
            ],
        )
