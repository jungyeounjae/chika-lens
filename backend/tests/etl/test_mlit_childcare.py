"""MLIT 육아·교육 집계 로직."""

from __future__ import annotations

from chika.domain.model.station import Station
from chika.etl.mlit_childcare import (
    Facility,
    count_near,
    deduplicate,
    parse_preschool,
    parse_school,
)


def _feature(properties: dict[str, object], lat: float = 35.7, lon: float = 139.7) -> dict:  # type: ignore[type-arg]
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def _station(station_id: str, lat: float, lon: float) -> Station:
    return Station(
        id=station_id, name_ja="駅", ward="新宿区", lat=lat, lon=lon, lines=("線",)
    )


# --- XKT007 幼稚園・保育所 ---


def test_a_kindergarten_is_counted_with_its_published_kind() -> None:
    facility = parse_preschool(
        _feature({"_id": "a", "schoolClassCode_name_ja": "幼稚園", "preSchoolName_ja": "は園"})
    )
    assert facility is not None
    assert facility.kind == "幼稚園"


def test_a_nursery_is_labelled_by_code_because_the_api_sends_no_name() -> None:
    """보육시설에는 종별 이름 필드가 아예 없다. 지어내지 않고 코드를 붙인다."""
    facility = parse_preschool(
        _feature({"_id": "a", "welfareFacilityMiddleClassCode": "0504"})
    )
    assert facility is not None
    assert facility.kind == "保育施設(0504)"


def test_a_closed_facility_is_excluded() -> None:
    """폐원한 곳을 세면 사라진 보육 정원이 점수로 남는다."""
    assert parse_preschool(_feature({"_id": "a", "closeSchoolCode": 1})) is None


def test_a_facility_without_a_point_is_skipped_not_placed_at_the_origin() -> None:
    assert parse_preschool({"properties": {"_id": "a"}, "geometry": None}) is None


# --- XKT006 学校 ---


def test_elementary_and_junior_high_are_counted() -> None:
    for kind in ("小学校", "中学校", "義務教育学校"):
        facility = parse_school(_feature({"_id": "a", "P29_003_name_ja": kind}))
        assert facility is not None, kind


def test_high_schools_and_universities_are_not_counted() -> None:
    """아이를 키우는 가구가 통학 거리를 따지는 것은 초등·중학이다.

    대학은 오히려 학생 거리(街)의 신호라 다른 지표와 뜻이 겹친다.
    """
    for kind in ("高等学校", "大学", "専修学校", "各種学校"):
        assert parse_school(_feature({"_id": "a", "P29_003_name_ja": kind})) is None


# --- 접기 ---


def test_a_facility_seen_in_two_tiles_is_counted_once() -> None:
    """타일은 여유 반경만큼 겹쳐 받는다. 중복을 두면 경계의 역만 부풀려진다."""
    same = [Facility("id-1", 35.7, 139.7, "幼稚園", "は園")] * 2
    assert len(deduplicate(same)) == 1


def test_facilities_without_an_id_are_dropped_rather_than_merged() -> None:
    nameless = [
        Facility("", 35.7, 139.7, "幼稚園", "a"),
        Facility("", 35.8, 139.8, "幼稚園", "b"),
    ]
    assert deduplicate(nameless) == []


def test_only_facilities_inside_the_radius_count() -> None:
    station = _station("st_a", 35.7000, 139.7000)
    near = Facility("near", 35.7000, 139.7050, "幼稚園", "가까움")   # 약 450m
    far = Facility("far", 35.7000, 139.7200, "幼稚園", "멂")        # 약 1.8km
    counts = count_near([station], [near, far], radius_m=800.0)
    assert counts == {"st_a": 1}


def test_a_station_with_no_facility_records_zero_not_missing() -> None:
    """공항·물류센터는 실제로 0이다. 결측으로 두면 퍼센타일 50을 받아버린다."""
    counts = count_near([_station("st_a", 35.7, 139.7)], [], radius_m=800.0)
    assert counts == {"st_a": 0}
