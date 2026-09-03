import pytest

from chika.etl.station_master import parse_stations, parse_ward_polygons, slugify_station

# 中野区 대용의 정사각형 폴리곤. 실제 좌표계(WGS84)와 같은 단위를 쓴다.
_N03 = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {"N03_001": "東京都", "N03_004": "中野区"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [139.60, 35.68],
                        [139.72, 35.68],
                        [139.72, 35.74],
                        [139.60, 35.74],
                        [139.60, 35.68],
                    ]
                ],
            },
        },
        {
            "properties": {"N03_001": "神奈川県", "N03_004": "横浜市"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [139.60, 35.40],
                        [139.72, 35.40],
                        [139.72, 35.46],
                        [139.60, 35.46],
                        [139.60, 35.40],
                    ]
                ],
            },
        },
    ],
}


def _station_feature(name: str, line: str, lon: float, lat: float) -> dict:
    """N02의 역 피처는 LineString(플랫폼 선)이다. 중점을 대표 좌표로 쓴다."""
    return {
        "properties": {"N02_003": line, "N02_004": "東日本旅客鉄道", "N02_005": name},
        "geometry": {"type": "LineString", "coordinates": [[lon - 0.001, lat], [lon + 0.001, lat]]},
    }


def test_slugify_uses_ascii_and_is_stable() -> None:
    assert slugify_station("中野") == slugify_station("中野")
    assert slugify_station("中野").isascii()
    assert slugify_station("中野") != slugify_station("新宿")


def test_parse_ward_polygons_keeps_only_tokyo() -> None:
    wards = parse_ward_polygons(_N03)
    assert [name for name, _ in wards] == ["中野区"]


def test_station_inside_a_ward_is_kept_with_its_ward_name() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [_station_feature("中野", "中央線", 139.66, 35.70)],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {"中野": "나카노"})
    assert len(stations) == 1
    assert stations[0].ward == "中野区"
    assert stations[0].name_ko == "나카노"
    assert stations[0].lon == pytest.approx(139.66)


def test_station_outside_the_23_wards_is_dropped() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [_station_feature("横浜", "東海道線", 139.66, 35.43)],
    }
    assert parse_stations(n02, parse_ward_polygons(_N03), {}) == []


def test_same_station_on_multiple_lines_is_merged() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [
            _station_feature("中野", "中央線", 139.66, 35.70),
            _station_feature("中野", "東西線", 139.661, 35.701),
        ],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert len(stations) == 1
    assert set(stations[0].lines) == {"中央線", "東西線"}


def test_korean_name_falls_back_to_japanese_when_unmapped() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [_station_feature("中野", "中央線", 139.66, 35.70)],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert stations[0].name_ko == "中野"


def test_output_is_sorted_by_id_for_deterministic_diffs() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [
            _station_feature("中野", "中央線", 139.66, 35.70),
            _station_feature("新宿", "山手線", 139.70, 35.69),
        ],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert [s.id for s in stations] == sorted(s.id for s in stations)
