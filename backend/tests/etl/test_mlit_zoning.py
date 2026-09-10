"""用途地域(XKT002) 파싱 — 住居専用地域 판별과 반경 안 면적 비율 계산."""

from __future__ import annotations

import pytest

from chika.etl.mlit_zoning import ZoningIndex, ZoningShapeError, parse_all, parse_zone

QUIET_IDS = frozenset({1, 2, 3, 4})


def _feature(youto_id: object, coords: list[list[float]], zone_id: str = "z1") -> dict:  # type: ignore[type-arg]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {"_id": zone_id, "youto_id": youto_id, "use_area_ja": "probe"},
    }


_BIG_SQUARE = [[139.0, 35.0], [139.0, 36.0], [140.0, 36.0], [140.0, 35.0], [139.0, 35.0]]


def test_low_rise_residential_is_quiet() -> None:
    zone = parse_zone(_feature(1, _BIG_SQUARE), QUIET_IDS)
    assert zone is not None
    assert zone.is_quiet is True


def test_commercial_is_not_quiet() -> None:
    zone = parse_zone(_feature(10, _BIG_SQUARE), QUIET_IDS)
    assert zone is not None
    assert zone.is_quiet is False


def test_missing_youto_id_fails_loudly() -> None:
    feature = _feature(1, _BIG_SQUARE)
    del feature["properties"]["youto_id"]  # type: ignore[index]
    with pytest.raises(ZoningShapeError, match="youto_id"):
        parse_zone(feature, QUIET_IDS)


def test_parse_all_deduplicates_by_zone_id() -> None:
    """타일 경계에 걸치면 같은 구역이 여러 타일에서 온다."""
    features = [_feature(1, _BIG_SQUARE, zone_id="z1")] * 3
    assert len(parse_all(features, QUIET_IDS)) == 1


def test_quiet_ratio_is_zero_with_nothing_nearby() -> None:
    index = ZoningIndex([])
    assert index.quiet_ratio_near(35.7, 139.7, radius_m=800.0) == 0.0


def test_quiet_ratio_is_one_when_fully_inside_a_quiet_zone() -> None:
    """반경 800m 를 통째로 덮는 거대한 住居専用 구역 하나뿐이면 비율은 1.0."""
    zone = parse_zone(_feature(1, _BIG_SQUARE), QUIET_IDS)
    assert zone is not None
    index = ZoningIndex([zone])
    assert index.quiet_ratio_near(35.7, 139.7, radius_m=800.0) == pytest.approx(1.0)


def test_quiet_ratio_is_zero_when_fully_inside_a_non_quiet_zone() -> None:
    zone = parse_zone(_feature(10, _BIG_SQUARE), QUIET_IDS)
    assert zone is not None
    index = ZoningIndex([zone])
    assert index.quiet_ratio_near(35.7, 139.7, radius_m=800.0) == pytest.approx(0.0)


def test_a_self_intersecting_zone_polygon_does_not_crash() -> None:
    """실측: 지자체 원본 폴리곤 일부가 자기교차라 GEOSException 이 났다.
    셰이프를 바꾸지 않고 위상만 고치는 buffer(0) 으로 복구해야 한다."""
    bowtie = [
        [139.0, 35.0], [140.0, 36.0], [140.0, 35.0], [139.0, 36.0], [139.0, 35.0],
    ]
    zone = parse_zone(_feature(1, bowtie), QUIET_IDS)
    assert zone is not None
    index = ZoningIndex([zone])
    ratio = index.quiet_ratio_near(35.7, 139.7, radius_m=800.0)
    assert 0.0 <= ratio <= 1.0


def test_quiet_ratio_reflects_a_partial_overlap() -> None:
    """반경 절반은 住居専用(quiet), 절반은 商業地域(not quiet)이면 대략 0.5."""
    lat0, lon0 = 35.7, 139.7
    # 동쪽 절반만 덮는 quiet 구역 — 둘 다 반경보다 훨씬 큰 사각형으로 확실히 덮는다.
    east_half = [
        [lon0, lat0 - 0.1], [lon0, lat0 + 0.1],
        [lon0 + 0.1, lat0 + 0.1], [lon0 + 0.1, lat0 - 0.1], [lon0, lat0 - 0.1],
    ]
    west_half = [
        [lon0 - 0.1, lat0 - 0.1], [lon0 - 0.1, lat0 + 0.1],
        [lon0, lat0 + 0.1], [lon0, lat0 - 0.1], [lon0 - 0.1, lat0 - 0.1],
    ]
    quiet = parse_zone(_feature(1, east_half, zone_id="q"), QUIET_IDS)
    busy = parse_zone(_feature(10, west_half, zone_id="b"), QUIET_IDS)
    assert quiet is not None and busy is not None
    index = ZoningIndex([quiet, busy])
    ratio = index.quiet_ratio_near(lat0, lon0, radius_m=500.0)
    assert ratio == pytest.approx(0.5, abs=0.02)
