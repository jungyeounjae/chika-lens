"""지표 24(주거전용지역 비율) 파싱과 집계 — MLIT XKT002(用途地域).

"조용함"을 직접 재는 지표는 없다. 대신 用途地域(국가 표준 12분류)에서
법적으로 상가·공장이 금지된 **住居専用地域**(1~4번, 低層·中高層)만 골라,
역 반경 800m 안에서 그 구역이 차지하는 **면적 비율**을 낸다 — 실제로
조용한지가 아니라 "법적으로 조용할 수밖에 없는 땅이 얼마나 되는가"의
대리 지표다.

`disaster_risk`(mlit_hazards.py)는 "가장 가까운 폴리곤까지 거리"를 쓰지만,
여기는 그 방식이 안 맞는다 — 반경 안에 여러 용도지역이 섞여 있고, 알고
싶은 건 거리가 아니라 **비중**이다. 그래서 면적 계산이 필요하고, 그러려면
위경도(도)가 아니라 미터 단위 평면으로 옮겨야 한다 — 경도 1도의 실제
길이가 위도에 따라 달라져서(도쿄 위도에서 위도 1도 ≈ 110.5km, 경도 1도
≈ 90.9km), 도 단위로 그냥 면적을 재면 동서로 늘어난 것처럼 보인다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shapely import STRtree
from shapely.affinity import affine_transform
from shapely.geometry import Point
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

#: 위경도 1도의 대략적인 미터 환산. 800m 반경 스케일에서 구면 곡률
#: 오차는 무시할 만하다 — 평면 근사로 충분하다.
_METERS_PER_DEGREE_LAT = 110_540.0
_METERS_PER_DEGREE_LON_AT_EQUATOR = 111_320.0


class ZoningShapeError(ValueError):
    """알려진 필드 구조가 아니다. 조용히 무시하면 비율이 소리 없이 틀어진다."""


@dataclass(frozen=True)
class ZonePolygon:
    zone_id: str
    geometry: BaseGeometry
    is_quiet: bool


def parse_zone(feature: dict[str, object], quiet_ids: frozenset[int]) -> ZonePolygon | None:
    """feature 하나를 심각도 대신 "住居専用 여부"가 붙은 폴리곤으로."""
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ZoningShapeError(f"properties 없음: {feature!r}")
    if "youto_id" not in properties:
        raise ZoningShapeError(f"youto_id 없음: {feature!r}")
    youto_id = properties["youto_id"]
    if not isinstance(youto_id, int):
        raise ZoningShapeError(f"youto_id 가 정수가 아니다: {youto_id!r}")

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise ZoningShapeError(f"geometry 없음: {feature!r}")

    return ZonePolygon(
        zone_id=str(properties.get("_id", "")),
        geometry=shapely_shape(geometry),
        is_quiet=youto_id in quiet_ids,
    )


def parse_all(
    features: Sequence[dict[str, object]], quiet_ids: frozenset[int]
) -> list[ZonePolygon]:
    """같은 구역이 타일 경계에 걸쳐 중복으로 오면 한 번만 남긴다."""
    seen: dict[str, ZonePolygon] = {}
    for feature in features:
        zone = parse_zone(feature, quiet_ids)
        if zone is None or not zone.zone_id or zone.zone_id in seen:
            continue
        seen[zone.zone_id] = zone
    return list(seen.values())


def _local_transform(lat0: float, lon0: float) -> tuple[float, ...]:
    """(lat0, lon0)를 원점으로 하는 위경도 -> 미터 평면 아핀 변환 행렬.

    shapely 좌표축은 (x=lon, y=lat) 순서다. 이 스케일만 적용하면 회전
    없는 평면 근사가 된다 — 800m 반경에서는 이걸로 충분하다.
    """
    lon_scale = _METERS_PER_DEGREE_LON_AT_EQUATOR * math.cos(math.radians(lat0))
    lat_scale = _METERS_PER_DEGREE_LAT
    # affine_transform 계수는 [a, b, d, e, xoff, yoff] (x' = a·x + b·y + xoff 식).
    return (lon_scale, 0.0, 0.0, lat_scale, -lon0 * lon_scale, -lat0 * lat_scale)


class ZoningIndex:
    """용도지역 폴리곤 집합. 역마다 반경 안 住居専用 면적 비율을 낸다."""

    def __init__(self, zones: Sequence[ZonePolygon]) -> None:
        self._zones = list(zones)
        self._tree = STRtree([z.geometry for z in self._zones])

    def quiet_ratio_near(self, lat: float, lon: float, radius_m: float) -> float:
        """반경 안에 걸리는 용도지역이 전혀 없으면 0.0 — 결측이 아니라
        "이 근방은 지정된 住居専用 구역이 없다"는 실측이다."""
        point = Point(lon, lat)
        # 후보 검색은 도(度) 단위 여유 버퍼로 — 정밀 계산은 아래 평면 변환 이후에 한다.
        search = point.buffer(radius_m * 1.5 / _METERS_PER_DEGREE_LON_AT_EQUATOR)
        candidates = self._tree.query(search)
        if len(candidates) == 0:
            return 0.0

        transform = _local_transform(lat, lon)
        circle = Point(0.0, 0.0).buffer(radius_m)
        quiet_area = 0.0
        for index in candidates:
            zone = self._zones[index]
            if not zone.is_quiet:
                continue
            local_zone = affine_transform(zone.geometry, transform)
            # 지자체 원본 폴리곤 중 일부가 자기교차 등으로 위상이 무효라
            # intersection 이 GEOSException 을 던진다(실측). buffer(0) 은
            # 셰이프를 바꾸지 않고 위상만 고치는 표준 셰이플리 처방이다.
            if not local_zone.is_valid:
                local_zone = local_zone.buffer(0)
            intersection = circle.intersection(local_zone)
            quiet_area += intersection.area

        return min(1.0, quiet_area / float(circle.area))
