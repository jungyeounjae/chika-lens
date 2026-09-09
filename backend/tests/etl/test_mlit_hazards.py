"""지표 14(재해위험) 파싱과 거리 감쇠. 프로브 실측 포맷을 그대로 쓴다."""

from __future__ import annotations

import pytest
from shapely.geometry import Point, Polygon, mapping

from chika.etl.mlit_hazards import (
    DECAY_M,
    HazardIndex,
    HazardShapeError,
    HazardZone,
    decayed_severity,
    flood_severity,
    liquefaction_severity,
    parse_all,
    parse_hazard,
    sediment_severity,
    storm_surge_severity,
)

#: 한 변이 약 200m인 정사각형. 도쿄 위도에서 대략적인 크기면 충분하다 —
#: 거리 계산 자체는 haversine 이 정확히 한다.
SQUARE = Polygon([(139.70, 35.70), (139.702, 35.70), (139.702, 35.702), (139.70, 35.702)])
INSIDE = (35.701, 139.701)  # (lat, lon) — 사각형 내부
FAR_AWAY = (35.80, 139.90)  # 수십km 밖


def _feature(properties: dict[str, object], polygon: Polygon = SQUARE) -> dict[str, object]:
    return {"geometry": mapping(polygon), "properties": properties}


# --- 레이어별 등급 -> 심각도 ---


def test_liquefaction_lower_level_is_more_severe() -> None:
    """실측 note 필드로 확인한 5단계 방향: 1=非常に液状化しやすい ~ 5=しにくい.

    489역 전체를 돌리기 전엔 저지대 4곳만 봐서 1~3, 6만 보였다 — 4·5가
    실제로 나타나서야 5단계였다는 걸 알았다.
    """
    assert (
        liquefaction_severity(1)  # type: ignore[operator]
        > liquefaction_severity(2)  # type: ignore[operator]
        > liquefaction_severity(3)  # type: ignore[operator]
        > liquefaction_severity(4)  # type: ignore[operator]
        > liquefaction_severity(5)  # type: ignore[operator]
    )


def test_liquefaction_level_6_is_excluded_not_zero() -> None:
    """評価対象外(河道 등)는 위험도 0이 아니라 신호 자체가 아니다."""
    assert liquefaction_severity(6) is None


def test_an_unknown_liquefaction_level_is_loud() -> None:
    with pytest.raises(HazardShapeError):
        liquefaction_severity(7)


def test_flood_higher_level_is_more_severe() -> None:
    """방향이 액상화와 반대다 — 想定最大規模 6단계, 클수록 위험."""
    assert flood_severity(1) < flood_severity(3) < flood_severity(6)


def test_flood_level_out_of_range_is_loud() -> None:
    with pytest.raises(HazardShapeError):
        flood_severity(7)


def test_storm_surge_bands_are_ordered_by_depth() -> None:
    assert (
        storm_surge_severity("0.3m未満")
        < storm_surge_severity("1m以上3m未満")
        < storm_surge_severity("10m以上20m未満")
    )


def test_an_unknown_storm_surge_band_is_loud() -> None:
    """새 침수심 구간이 오면 등급표를 갱신해야 한다는 뜻이다.

    "20m以上"이 진짜 존재하는지는 확인 안 됐다 — 확인 안 된 값을 통과시키지
    않는다는 것 자체가 이 테스트의 요점이다.
    """
    with pytest.raises(HazardShapeError):
        storm_surge_severity("20m以上")


def test_sediment_red_zone_outranks_yellow_zone() -> None:
    """1=Yellow(지정완료), 2=Red(지정완료)."""
    assert sediment_severity(2) > sediment_severity(1)


def test_sediment_designation_stage_does_not_change_severity() -> None:
    """489역 전체에서 3·4(지정 전/조사단계)가 나와 2단계인 줄 알았던 매핑을
    다시 확인했다 — 지정 절차 차이일 뿐 위험 정도는 완료분과 같다."""
    assert sediment_severity(1) == sediment_severity(3)
    assert sediment_severity(2) == sediment_severity(4)
    assert sediment_severity(3) < sediment_severity(4)


def test_an_unknown_sediment_degree_code_is_loud() -> None:
    with pytest.raises(HazardShapeError):
        sediment_severity(5)


# --- feature 파싱 ---


def test_parse_hazard_reads_the_layer_specific_field() -> None:
    zone = parse_hazard(_feature({"A31a_205": 3}), "flood")
    assert zone is not None
    assert zone.severity == pytest.approx(0.5)


def test_parse_hazard_skips_excluded_liquefaction_polygons() -> None:
    assert parse_hazard(_feature({"liquefaction_tendency_level": 6}), "liquefaction") is None


def test_parse_hazard_requires_the_expected_field() -> None:
    with pytest.raises(HazardShapeError):
        parse_hazard(_feature({"A49_003": "1m以上3m未満"}), "flood")


def test_parse_all_drops_excluded_and_keeps_the_rest() -> None:
    features = [
        _feature({"liquefaction_tendency_level": 1}),
        _feature({"liquefaction_tendency_level": 6}),
        _feature({"liquefaction_tendency_level": 2}),
    ]
    assert len(parse_all(features, "liquefaction")) == 2


# --- 거리 감쇠 ---


def test_inside_the_polygon_keeps_full_severity() -> None:
    assert decayed_severity(1.0, 0.0) == 1.0


def test_severity_decays_linearly_with_distance() -> None:
    assert decayed_severity(1.0, DECAY_M / 2) == pytest.approx(0.5)


def test_severity_is_zero_beyond_the_decay_window() -> None:
    assert decayed_severity(1.0, DECAY_M * 2) == 0.0


# --- HazardIndex ---


def test_a_station_inside_a_hazard_polygon_gets_its_full_severity() -> None:
    index = HazardIndex([HazardZone(geometry=SQUARE, severity=0.8)])
    assert index.risk_near(*INSIDE) == pytest.approx(0.8)


def test_a_station_far_from_every_polygon_is_not_missing_but_zero() -> None:
    """반경 안에 하자드가 없다는 것은 결측이 아니라 '위험 없음'이라는 사실이다."""
    index = HazardIndex([HazardZone(geometry=SQUARE, severity=1.0)])
    assert index.risk_near(*FAR_AWAY) == 0.0


def test_a_station_takes_the_worst_of_several_overlapping_layers() -> None:
    """4개 레이어를 합쳐도 결과는 '전체 최댓값'과 같다 — 레이어를 구분해 들고
    다닐 필요가 없다는 설계 전제를 확인한다."""
    weak = Polygon([(139.70, 35.70), (139.7005, 35.70), (139.7005, 35.7005), (139.70, 35.7005)])
    index = HazardIndex(
        [HazardZone(geometry=weak, severity=0.3), HazardZone(geometry=SQUARE, severity=0.9)]
    )
    assert index.risk_near(*INSIDE) == pytest.approx(0.9)


def test_point_on_the_boundary_counts_as_inside() -> None:
    lon, lat = SQUARE.exterior.coords[0]
    index = HazardIndex([HazardZone(geometry=SQUARE, severity=0.7)])
    assert index.risk_near(lat, lon) == pytest.approx(0.7)


def test_an_empty_index_is_always_zero() -> None:
    assert HazardIndex([]).risk_near(*INSIDE) == 0.0


def test_geometry_round_trips_through_geojson_mapping() -> None:
    """실제 배치는 GeoJSON dict 를 받는다 — Polygon 객체가 아니라."""
    zone = parse_hazard(_feature({"A31a_205": 6}), "flood")
    assert zone is not None
    assert Point(139.701, 35.701).within(zone.geometry)
