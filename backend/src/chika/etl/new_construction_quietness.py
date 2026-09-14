"""신축 물건 좌표 -> 최근접 역 + 그 역의 일평균 승하차인원(정숙도 프록시).

정숙도 자체를 새로 계산하지 않는다 — 이미 배치로 계산된 역별
daily_ridership(build_ridership.py, MetricKey.DAILY_RIDERSHIP)을 재사용한다.
승하차인원이 많을수록 시끄러운 역세권이라는 게 이 지표의 기존 해석이다
(AreaMap.tsx의 DIRECTIONLESS_METRICS 참고 — "많다/적다"이지 "좋다/나쁘다"가
아니므로, 이 값을 '조용함' 점수로 뒤집는 건 이 모듈의 소비자 몫이다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from chika.domain.model.station import Station
from chika.domain.service.geo import distance_meters


@dataclass(frozen=True)
class Quietness:
    station_id: str
    station_name: str
    distance_m: float
    #: 결측이면 None — 표본 부족(MIN_SAMPLES)으로 아직 계산 안 된 역일 수 있다.
    daily_ridership: float | None


def nearest_quietness(
    lat: float,
    lon: float,
    stations: Sequence[Station],
    ridership: Mapping[str, float],
) -> Quietness | None:
    """역 목록이 비어 있으면 None. 최근접 역의 승하차인원이 ridership 인덱스에
    없으면(결측) daily_ridership을 None으로 — 0으로 채우지 않는다."""
    if not stations:
        return None
    nearest = min(stations, key=lambda s: distance_meters(lat, lon, s.lat, s.lon))
    distance = distance_meters(lat, lon, nearest.lat, nearest.lon)
    return Quietness(
        station_id=nearest.id,
        station_name=nearest.name_ja,
        distance_m=distance,
        daily_ridership=ridership.get(nearest.id),
    )
