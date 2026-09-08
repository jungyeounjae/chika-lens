"""지표 11(육아·교육)을 MLIT 시설 등록부에서 접는 순수 로직.

Google Aggregate 는 개수만 돌려줘서 무엇이 세어졌는지 알 수 없었다. MLIT 는
시설 하나하나를 좌표와 종별과 함께 주므로, 무엇을 세고 무엇을 뺐는지 코드에
남는다 — 그래서 "학원이 섞였을 수 있다"는 주의문이 필요 없어진다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from chika.domain.model.station import Station
from chika.domain.service.geo import distance_meters
from chika.etl.mlit_datasets import SCHOOL_KINDS_COUNTED


@dataclass(frozen=True)
class Facility:
    """집계 대상 시설 한 곳."""

    facility_id: str
    lat: float
    lon: float
    kind: str
    name: str


def _point(feature: Mapping[str, object]) -> tuple[float, float] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, Sequence) or len(coordinates) < 2:
        return None
    lon, lat = float(coordinates[0]), float(coordinates[1])
    return lat, lon


def parse_preschool(feature: Mapping[str, object]) -> Facility | None:
    """XKT007 (幼稚園・保育所). 폐원한 곳은 뺀다."""
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        return None
    if str(properties.get("closeSchoolCode", "0")) not in {"0", ""}:
        return None
    point = _point(feature)
    if point is None:
        return None
    # 유치원에는 `schoolClassCode_name_ja` 가 오지만 보육시설에는 코드만 온다 —
    # 이름 필드가 아예 없다. 종별을 지어내지 않고 코드를 그대로 붙인다.
    # 대분류 05 는 児童福祉施設 이고, 표본을 훑어보면 하위 코드는 모두
    # 保育所·認定こども園·保育室·사업소내 보육시설이었다 (2026-09-08 실측).
    kind = str(properties.get("schoolClassCode_name_ja") or "")
    if not kind:
        code = str(properties.get("welfareFacilityMiddleClassCode", "")) or "?"
        kind = f"保育施設({code})"
    return Facility(
        facility_id=str(properties.get("_id", "")),
        lat=point[0],
        lon=point[1],
        kind=kind,
        name=str(properties.get("preSchoolName_ja", "")),
    )


def parse_school(feature: Mapping[str, object]) -> Facility | None:
    """XKT006 (学校). 초등·중학만 센다 — 근거는 mlit_datasets 에 있다."""
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        return None
    kind = str(properties.get("P29_003_name_ja", ""))
    if kind not in SCHOOL_KINDS_COUNTED:
        return None
    point = _point(feature)
    if point is None:
        return None
    return Facility(
        facility_id=str(properties.get("_id", "")),
        lat=point[0],
        lon=point[1],
        kind=kind,
        name=str(properties.get("P29_004_ja", "")),
    )


def deduplicate(facilities: Iterable[Facility]) -> list[Facility]:
    """같은 시설이 여러 타일에 걸쳐 오면 한 번만 센다.

    타일은 공간을 나누지만 여유 반경 때문에 이웃 타일을 겹쳐 받는다. 중복을
    두면 경계에 있는 역만 부풀려진다.
    """
    seen: dict[str, Facility] = {}
    for facility in facilities:
        if facility.facility_id and facility.facility_id not in seen:
            seen[facility.facility_id] = facility
    return list(seen.values())


def count_near(
    stations: Sequence[Station],
    facilities: Sequence[Facility],
    radius_m: float,
) -> dict[str, int]:
    """역마다 반경 안의 시설 수. 0건도 결측이 아니라 측정된 0으로 남긴다."""
    return {
        station.id: sum(
            1
            for facility in facilities
            if distance_meters(station.lat, station.lon, facility.lat, facility.lon)
            <= radius_m
        )
        for station in stations
    }
