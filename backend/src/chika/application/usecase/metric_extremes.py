"""전 역(489개) 기준 지표 극값 — "홍수가 잦은 곳은?", "치안이 나쁜 곳은?"
처럼 비교 기준(다이얼) 없이 지표 하나만으로 최악/최선을 물을 때 답한다.

`MetricDistribution`은 한 역 반경(1.5km)만 보고, `RankAreas`는 다이얼 가중
종합점수다 — 둘 다 "489역 전체에서 지표 하나로 최악을 꼽아라"에는 못 쓴다.
그 정렬을 실제로 여기서 한다.

**정렬을 코드가 한다.** percentile 은 이미 "높을수록 좋다/안전하다"로
통일돼 있다(NEGATIVE_METRICS 는 정규화 단계에서 뒤집힌다) — LLM이 raw_value
방향과 percentile 방향을 다시 대조해 뒤집을 필요가 없게, 결과 자체를
이미 원하는 순서로 정렬해서 낸다. "재해위험이 낮은 역"을 물었는데 안전한
역(percentile 90+)을 골라 답한 사례가 있었다 — 프롬프트로 방향을 설명하는
것만으로는 매번 지켜지지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository
from chika.domain.service.normalization import normalize

#: 지도·서술이 감당할 수 있는 상한.
MAX_RESULTS = 10


@dataclass(frozen=True)
class ExtremePoint:
    station: Station
    percentile: float
    raw_value: float | None


class MetricExtremes:
    def __init__(self, areas: AreaMetricsRepository) -> None:
        self._areas = areas

    def execute(self, metric: MetricKey, worst_first: bool, limit: int) -> list[ExtremePoint]:
        """`worst_first=True` 면 percentile 오름차순(가장 나쁜 역부터).

        결측(`is_missing`)인 역은 뺀다 — 결측은 중립값 50.0 으로 채워져
        있어서, 포함시키면 "재해위험 데이터가 없는 역"이 "중간 정도로
        위험한 역"으로 둔갑한다.
        """
        raws = self._areas.raw_metrics()
        raw_by_id = {r.station_id: r for r in raws}
        stations_by_id = {s.id: s for s in self._areas.stations()}

        points = [
            ExtremePoint(
                station=stations_by_id[area.station_id],
                percentile=area.percentile[metric],
                raw_value=raw_by_id[area.station_id].get(metric),
            )
            for area in normalize(raws)
            if metric not in area.missing and area.station_id in stations_by_id
        ]
        points.sort(key=lambda p: p.percentile, reverse=not worst_first)

        capped = max(1, min(limit, MAX_RESULTS))
        return points[:capped]
