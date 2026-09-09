"""역 하나를 중심으로 반경 안 역들의 지표 분포 (지도 색칠용).

MLIT 이용 목적 회신 서약(스펙 §3.1.2)은 "역권 단위로 집계해 정규화한 값만
쓰고, 개별 원자료를 그대로 표시하지 않는다"고 못 박는다. 그래서 재해위험
등 MLIT 유래 지표의 원본 Polygon은 지도에 그릴 수 없다 — 이 유스케이스는
그 대신 **우리가 이미 정규화한 역 단위 백분위**만 점으로 낸다. 원본 구역
경계가 아니라 우리 계산 결과이므로 서약 밖이다.

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
