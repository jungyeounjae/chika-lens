"""지표 기여도 분해 (스펙 §2.1 '왜 여기가 1위인가').

LLM에 넘길 재료만 만든다. 문장은 만들지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import WARD_RESOLUTION_METRICS, AreaMetrics, MetricKey
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, Weights
from chika.domain.repository import AreaMetricsRepository, PriceRepository
from chika.domain.service.dials import DIAL_TO_METRICS, expand_dials
from chika.domain.service.geo import distance_meters
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDetail:
    key: MetricKey
    percentile: float
    #: 정규화 이전의 실제 값(공원 68개 등).
    #: 백분위만으로는 "몇 개야?" 에 답할 수 없다.
    raw_value: float | None
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
    #: 활성 다이얼(강도>0)마다 그 다이얼에 속한 지표 전부. strengths/
    #: weaknesses는 전체 지표 중 기여도 상위·하위 top_n개뿐이라, 다이얼이
    #: 여럿 활성화되면 한 다이얼의 지표 전부가 더 극단적인 다른 다이얼에
    #: 밀려 안 보일 수 있다 — "육아 환경을 함께 봤다"고 말해 놓고 육아
    #: 지표를 하나도 못 보여주는 사고가 실제로 났다. 이 필드는 그 다이얼을
    #: 언급한 이상 최소한 근거를 낼 수 있게, 안 보이는 지표까지 전부 준다.
    by_dial: dict[Dial, list[MetricDetail]]
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

        raws = self._areas.raw_metrics()
        area = _find_area(normalize(raws), station_id)
        raw = next((r for r in raws if r.station_id == station_id), None)
        # focus_metric 이 있으면(예: "초등학교 몇개야?") 다이얼 전개를
        # 건너뛰고 그 지표 하나에만 가중치 1.0을 준다 — rank_areas 와 같은
        # 이유다. 안 그러면 다이얼이 전부 0이라 균등 다이얼로 대체되고,
        # strengths/weaknesses(기여도 상위·하위 3개)에 focus_metric 이
        # 안 뜬 채로 "데이터 없음"이라고 잘못 답하게 된다.
        weights = (
            Weights({criteria.focus_metric: 1.0})
            if criteria.focus_metric is not None
            else expand_dials(criteria.dials)
        )
        area_score = score(area, weights)

        def detail(key: MetricKey) -> MetricDetail:
            return MetricDetail(
                key=key,
                percentile=area.percentile[key],
                raw_value=raw.get(key) if raw is not None else None,
                contribution=area_score.contributions[key],
                is_missing=key in area.missing,
                is_ward_resolution=key in WARD_RESOLUTION_METRICS,
            )

        by_dial = {
            dial: [detail(key) for key in DIAL_TO_METRICS[dial]]
            for dial in Dial
            if criteria.dials.strength(dial) > 0
        }

        return AreaExplanation(
            station=station,
            nearby=_nearby(station, self._areas.stations()),
            total=area_score.total,
            rent_yen=self._prices.median_rents(criteria.household).get(station_id),
            strengths=[detail(key) for key, _ in area_score.top_drivers(top_n)],
            weaknesses=[detail(key) for key, _ in area_score.bottom_drivers(top_n)],
            by_dial=by_dial,
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
