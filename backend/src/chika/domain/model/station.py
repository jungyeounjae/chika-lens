"""역 마스터. 분석 단위는 역 반경 800m (스펙 §6.1)."""

from __future__ import annotations

from dataclasses import dataclass

#: 도쿄 23구를 넉넉히 감싸는 경계 상자. 좌표 오염을 조기에 잡기 위한 방어선.
TOKYO_BBOX = (35.50, 35.85, 139.55, 139.95)  # lat_min, lat_max, lon_min, lon_max

STATION_RADIUS_METERS = 800


@dataclass(frozen=True)
class Station:
    id: str
    name_ja: str
    ward: str
    lat: float
    lon: float
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        lat_min, lat_max, lon_min, lon_max = TOKYO_BBOX
        if not (lat_min <= self.lat <= lat_max and lon_min <= self.lon <= lon_max):
            raise ValueError(
                f"station {self.id!r} is outside Tokyo: ({self.lat}, {self.lon})"
            )
