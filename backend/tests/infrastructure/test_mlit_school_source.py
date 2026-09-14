"""MlitSchoolFacilitySource — 실시간 MLIT 조회(XKT006/XKT007) + 거리 필터링."""

from __future__ import annotations

import json

from chika.etl.mlit_client import MlitClient
from chika.infrastructure.mlit_school_source import MlitSchoolFacilitySource

#: 조회 좌표 — 光が丘역 근방(実測 주소는 아니고 테스트용 임의 좌표).
QUERY_LAT, QUERY_LON = 35.760, 139.609
NEAR_LAT, NEAR_LON = 35.7605, 139.6095  # QUERY 로부터 약 70m
FAR_LAT, FAR_LON = 35.90, 139.90  # 수십km 밖


def _preschool_feature(
    facility_id: str, name: str, lat: float = NEAR_LAT, lon: float = NEAR_LON
) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "_id": facility_id,
            "_index": "bs006_preschool_001",
            "schoolClassCode_name_ja": "幼稚園",
            "preSchoolName_ja": name,
        },
    }


def _school_feature(
    facility_id: str, name: str, kind: str = "小学校", lat: float = NEAR_LAT, lon: float = NEAR_LON
) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "_id": facility_id,
            "_index": "bs005_school_001",
            "P29_003_name_ja": kind,
            "P29_004_ja": name,
        },
    }


def _client_returning(features_by_endpoint: dict[str, list[dict[str, object]]]) -> MlitClient:
    def transport(url: str, _headers: dict[str, str]) -> tuple[bytes, str]:
        for endpoint, features in features_by_endpoint.items():
            if f"/{endpoint}" in url:
                return json.dumps({"type": "FeatureCollection", "features": features}).encode(), ""
        return json.dumps({"type": "FeatureCollection", "features": []}).encode(), ""

    return MlitClient("test-key", transport=transport, sleep=lambda _: None)


def test_a_preschool_near_the_point_is_returned_with_distance() -> None:
    client = _client_returning({"XKT007": [_preschool_feature("p1", "ひかり幼稚園")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1
    assert facilities[0].name == "ひかり幼稚園"
    assert facilities[0].kind == "幼稚園"
    assert facilities[0].distance_m < 800.0


def test_a_school_near_the_point_is_returned() -> None:
    client = _client_returning({"XKT006": [_school_feature("s1", "光が丘第八小学校")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1
    assert facilities[0].name == "光が丘第八小学校"
    assert facilities[0].kind == "小学校"


def test_a_facility_far_beyond_the_radius_is_dropped() -> None:
    client = _client_returning(
        {"XKT006": [_school_feature("s1", "먼학교", lat=FAR_LAT, lon=FAR_LON)]}
    )
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert facilities == []


def test_a_high_school_is_excluded_not_zero() -> None:
    """SCHOOL_KINDS_COUNTED(초등·중학·義務教育学校)만 센다 — parse_school의 기존
    동작을 그대로 물려받는다(mlit_childcare.py 기존 로직, 새로 만드는 필터가
    아니다)."""
    client = _client_returning({"XKT006": [_school_feature("s1", "고교", kind="高等学校")]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert facilities == []


def test_duplicate_features_across_tiles_are_deduplicated_by_id() -> None:
    feature = _preschool_feature("dup", "중복유치원")
    client = _client_returning({"XKT007": [feature, feature]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(facilities) == 1


def test_preschools_and_schools_are_combined_and_sorted_by_distance() -> None:
    far = _preschool_feature("p1", "먼유치원", lat=QUERY_LAT + 0.003, lon=QUERY_LON + 0.003)
    close_but_in_radius = _school_feature(
        "s1", "가까운학교", lat=NEAR_LAT, lon=NEAR_LON
    )
    client = _client_returning({"XKT007": [far], "XKT006": [close_but_in_radius]})
    source = MlitSchoolFacilitySource(client)

    facilities = source.facilities_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert [f.name for f in facilities] == ["가까운학교", "먼유치원"]
    assert facilities[0].distance_m < facilities[1].distance_m
