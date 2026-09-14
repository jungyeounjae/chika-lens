"""MlitZoningPolygonSource — 실시간 MLIT 조회 + 거리 필터링 + 높이 매핑."""

from __future__ import annotations

import json

from shapely.geometry import Polygon, mapping

from chika.etl.mlit_client import MlitClient
from chika.infrastructure.mlit_zoning_source import MlitZoningPolygonSource

NEAR_SQUARE = Polygon([(139.70, 35.70), (139.702, 35.70), (139.702, 35.702), (139.70, 35.702)])
STATION_LAT, STATION_LON = 35.701, 139.701
FAR_AWAY_LAT, FAR_AWAY_LON = 35.90, 139.90
_ZONING_INDEX = "bs001_use_area"
_LOW_RISE = "第一種低層住居専用地域"


def _feature(properties: dict[str, object], polygon: Polygon = NEAR_SQUARE) -> dict[str, object]:
    return {"geometry": mapping(polygon), "properties": properties}


def _low_rise_feature(feature_id: str) -> dict[str, object]:
    return _feature(
        {
            "youto_id": 1,
            "use_area_ja": _LOW_RISE,
            "_id": feature_id,
            "_index": _ZONING_INDEX,
        }
    )


def _client_returning(features: list[dict[str, object]]) -> MlitClient:
    def transport(_url: str, _headers: dict[str, str]) -> tuple[bytes, str]:
        return json.dumps({"type": "FeatureCollection", "features": features}).encode(), ""

    return MlitClient("test-key", transport=transport, sleep=lambda _: None)


def test_a_low_rise_residential_zone_gets_a_low_height() -> None:
    client = _client_returning([_low_rise_feature("z1")])
    source = MlitZoningPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=500.0)

    assert len(polygons) == 1
    assert polygons[0].height_m == 10.0
    assert polygons[0].use_area_ja == _LOW_RISE


def test_a_commercial_zone_gets_the_tallest_height() -> None:
    feature = _feature(
        {"youto_id": 10, "use_area_ja": "商業地域", "_id": "z2", "_index": _ZONING_INDEX}
    )
    client = _client_returning([feature])
    source = MlitZoningPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=500.0)

    assert polygons[0].height_m == 60.0


def test_a_polygon_far_beyond_the_radius_is_dropped() -> None:
    client = _client_returning([_low_rise_feature("z1")])
    source = MlitZoningPolygonSource(client)

    polygons = source.polygons_near(FAR_AWAY_LAT, FAR_AWAY_LON, radius_m=500.0)

    assert polygons == []


def test_duplicate_features_across_tiles_are_deduplicated_by_id() -> None:
    feature = _low_rise_feature("dup")
    client = _client_returning([feature, feature])
    source = MlitZoningPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=500.0)

    assert len(polygons) == 1
