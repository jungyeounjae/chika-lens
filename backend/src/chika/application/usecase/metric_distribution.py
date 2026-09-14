"""역 하나를 중심으로 반경 안 역들의 지표 분포 (지도 색칠용).

이전에는 "MLIT 이용 목적 회신 서약(스펙 §3.1.2)이 원자료를 그대로 표시하지
않는다고 못 박는다"고 여기 적혀 있었다 — 그런 서약은 없었다(2026-09-11
정정, 스펙 §3.1.2 참고). 실제 이용약관(PDL1.0)은 출처 표기 조건으로 원본
Polygon 표시도 허용한다. 그래도 이 유스케이스는 **우리가 정규화한 역 단위
백분위**만 낸다 — 원본 구역 경계는 역세권 격자와 해상도가 달라 "이 역
반경의 위험도"라는 질문에 직접 답이 안 되고, 정규화된 값이라야 지표마다
다른 등급 체계(액상화 5단계·홍수 6단계 등)를 percentile 하나로 통일해
비교할 수 있다 — 지금은 이게 라이선스가 아니라 설계상 더 쓸모 있는
선택이라 유지한다.

가중치가 없다 — 다이얼도 조건도 필요 없이 지표 하나의 백분위만 본다.
"어디가 넓게 위험한가"를 보는 게 목적이지 종합 점수 순위가 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository
from chika.domain.service.geo import distance_meters
from chika.domain.service.normalization import normalize

#: 주변 역 탐색 반경. explain_area의 NEARBY_RADIUS_M과 같은 값 —
#: 지도에서 두 기능이 다른 반경으로 보이면 사용자가 일관성을 의심한다.
RADIUS_M = 1_500.0

#: 지도가 읽히는 한계. 신주쿠 일대는 이 반경에 역이 수십 개 있다.
MAX_POINTS = 12


@dataclass(frozen=True)
class DistributionPoint:
    station: Station
    percentile: float
    #: 정규화 이전의 실제 값. `None`이면 raw 자체가 없다는 뜻이다.
    raw_value: float | None
    is_missing: bool
    distance_m: float


class MetricDistribution:
    def __init__(self, areas: AreaMetricsRepository) -> None:
        self._areas = areas

    def execute(
        self, station_id: str, metric: MetricKey, radius_m: float = RADIUS_M
    ) -> list[DistributionPoint]:
        stations = list(self._areas.stations())
        origin = next((s for s in stations if s.id == station_id), None)
        if origin is None:
            raise KeyError(f"unknown station: {station_id}")

        raws = self._areas.raw_metrics()
        raw_by_id = {r.station_id: r for r in raws}
        area_by_id = {a.station_id: a for a in normalize(raws)}

        points: list[DistributionPoint] = []
        for station in stations:
            distance = distance_meters(origin.lat, origin.lon, station.lat, station.lon)
            if station.id != origin.id and distance > radius_m:
                continue
            area = area_by_id.get(station.id)
            if area is None:
                continue
            raw = raw_by_id.get(station.id)
            points.append(
                DistributionPoint(
                    station=station,
                    percentile=area.percentile[metric],
                    raw_value=raw.get(metric) if raw is not None else None,
                    is_missing=metric in area.missing,
                    distance_m=distance,
                )
            )

        points.sort(key=lambda p: (p.distance_m, p.station.id))
        return points[:MAX_POINTS]
