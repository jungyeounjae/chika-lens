"""MlitHazardPolygonSource — 실시간 MLIT 조회 + 거리 필터링 + 심각도 변환."""

from __future__ import annotations

import json

from shapely.geometry import Polygon, mapping

from chika.etl.mlit_client import MlitClient
from chika.infrastructure.mlit_hazard_source import MlitHazardPolygonSource

#: 도쿄 위도에서 대략 200m 짜리 사각형.
NEAR_SQUARE = Polygon([(139.70, 35.70), (139.702, 35.70), (139.702, 35.702), (139.70, 35.702)])
STATION_LAT, STATION_LON = 35.701, 139.701  # NEAR_SQUARE 내부
FAR_AWAY_LAT, FAR_AWAY_LON = 35.90, 139.90  # 수십km 밖


def _feature(properties: dict[str, object], polygon: Polygon = NEAR_SQUARE) -> dict[str, object]:
    return {"geometry": mapping(polygon), "properties": properties}


def _client_returning(features_by_endpoint: dict[str, list[dict[str, object]]]) -> MlitClient:
    def transport(url: str, _headers: dict[str, str]) -> tuple[bytes, str]:
        for endpoint, features in features_by_endpoint.items():
            if f"/{endpoint}" in url:
                return json.dumps({"type": "FeatureCollection", "features": features}).encode(), ""
        return json.dumps({"type": "FeatureCollection", "features": []}).encode(), ""

    return MlitClient("test-key", transport=transport, sleep=lambda _: None)


_FLOOD_INDEX = "bs030_flood_area_maximum_scale"
_SEDIMENT_INDEX = "bs031_sediment_disaster_alert_area"
_LIQUEFACTION_INDEX = "bs028_liquefaction_tendency_map"
_STORM_SURGE_INDEX = "bs033_storm_surge_area"
_TSUNAMI_INDEX = "bs032_tsunami_area"


def test_a_flood_polygon_near_the_point_is_returned_with_severity_and_label() -> None:
    feature = _feature({"A31a_205": 3, "_id": "f1", "_index": _FLOOD_INDEX})
    client = _client_returning({"XKT026": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    flood = [p for p in polygons if p.layer == "flood"]
    assert len(flood) == 1
    assert flood[0].severity == 3 / 6
    assert flood[0].label == "3.0m~5.0m"


def test_a_sediment_polygon_carries_its_yellow_red_label() -> None:
    feature = _feature({"A33_002": 2, "_id": "s1", "_index": _SEDIMENT_INDEX})
    client = _client_returning({"XKT029": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    sediment = [p for p in polygons if p.layer == "sediment"]
    assert len(sediment) == 1
    assert "레드존" in sediment[0].label


def test_a_polygon_far_beyond_the_radius_is_dropped() -> None:
    feature = _feature({"A31a_205": 3, "_id": "f1", "_index": _FLOOD_INDEX})
    client = _client_returning({"XKT026": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(FAR_AWAY_LAT, FAR_AWAY_LON, radius_m=800.0)

    assert polygons == []


def test_duplicate_features_across_tiles_are_deduplicated_by_id() -> None:
    feature = _feature({"A31a_205": 1, "_id": "dup", "_index": _FLOOD_INDEX})
    client = _client_returning({"XKT026": [feature, feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    assert len([p for p in polygons if p.layer == "flood"]) == 1


def test_a_liquefaction_polygon_carries_its_level_out_of_five() -> None:
    feature = _feature(
        {"liquefaction_tendency_level": 1, "_id": "l1", "_index": _LIQUEFACTION_INDEX}
    )
    client = _client_returning({"XKT025": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    liquefaction = [p for p in polygons if p.layer == "liquefaction"]
    assert len(liquefaction) == 1
    assert liquefaction[0].severity == 1.0  # 레벨1 = 가장 위험
    assert "1/5" in liquefaction[0].label


def test_liquefaction_level_6_is_excluded_not_zero() -> None:
    """評価対象外(河道 등) — mlit_hazards.liquefaction_severity 와 같은 동작."""
    feature = _feature(
        {"liquefaction_tendency_level": 6, "_id": "l2", "_index": _LIQUEFACTION_INDEX}
    )
    client = _client_returning({"XKT025": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    assert [p for p in polygons if p.layer == "liquefaction"] == []


def test_a_storm_surge_polygon_carries_its_korean_band_label() -> None:
    feature = _feature({"A49_003": "1m以上3m未満", "_id": "s1", "_index": _STORM_SURGE_INDEX})
    client = _client_returning({"XKT027": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    storm_surge = [p for p in polygons if p.layer == "storm_surge"]
    assert len(storm_surge) == 1
    assert storm_surge[0].label == "1m~3m"


def test_a_tsunami_polygon_carries_its_raw_band_as_label() -> None:
    feature = _feature({"A40_003": "1m以上 ～ 2m未満", "_id": "t1", "_index": _TSUNAMI_INDEX})
    client = _client_returning({"XKT028": [feature]})
    source = MlitHazardPolygonSource(client)

    polygons = source.polygons_near(STATION_LAT, STATION_LON, radius_m=800.0)

    tsunami = [p for p in polygons if p.layer == "tsunami"]
    assert len(tsunami) == 1
    assert tsunami[0].label == "1m以上 ～ 2m未満"
