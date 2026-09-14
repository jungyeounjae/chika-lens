"""OverpassParkSource — Overpass 응답 파싱 + GeoJSON 변환."""

from __future__ import annotations

import json

import pytest

from chika.etl.overpass_client import OverpassClient, OverpassFetchError
from chika.infrastructure.overpass_park_source import OverpassParkSource

QUERY_LAT, QUERY_LON = 35.760, 139.609


def _client_returning(elements: list[dict[str, object]]) -> OverpassClient:
    def transport(url: str, body: bytes) -> bytes:
        return json.dumps({"elements": elements}).encode()

    return OverpassClient(transport=transport, sleep=lambda _: None)


def _way(name: str | None, points: list[tuple[float, float]]) -> dict[str, object]:
    """points 는 (lat, lon) 순서 — Overpass `out geom` 응답과 동일."""
    element: dict[str, object] = {
        "type": "way",
        "geometry": [{"lat": lat, "lon": lon} for lat, lon in points],
    }
    if name is not None:
        element["tags"] = {"name": name}
    return element


_SQUARE = [
    (35.759, 139.608),
    (35.759, 139.610),
    (35.761, 139.610),
    (35.761, 139.608),
    (35.759, 139.608),
]


def test_a_named_park_is_parsed_with_its_polygon() -> None:
    client = _client_returning([_way("北原公園", _SQUARE)])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert len(polygons) == 1
    assert polygons[0].name == "北原公園"
    assert polygons[0].geometry["type"] == "Polygon"
    coordinates = polygons[0].geometry["coordinates"]
    assert coordinates[0][0] == [139.608, 35.759]  # [lon, lat] 순서로 변환됐는지


def test_a_park_without_a_name_stays_none() -> None:
    """OSM 에 이름이 없는 공원도 있다 — 지어내지 않는다."""
    client = _client_returning([_way(None, _SQUARE)])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert polygons[0].name is None


def test_a_way_with_too_few_points_is_skipped() -> None:
    client = _client_returning([_way("점두개", [(35.759, 139.608), (35.760, 139.609)])])
    source = OverpassParkSource(client)

    polygons = source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)

    assert polygons == []


def test_no_elements_returns_an_empty_list() -> None:
    client = _client_returning([])
    source = OverpassParkSource(client)

    assert source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0) == []


def test_non_json_response_raises_overpass_fetch_error() -> None:
    """게이트웨이 오류 페이지가 HTTP 200으로 오면 JSON 파싱이 아니라 에러여야 한다."""
    client = OverpassClient(
        transport=lambda url, body: b"<html>Bad Gateway</html>", sleep=lambda _: None
    )
    source = OverpassParkSource(client)

    with pytest.raises(OverpassFetchError):
        source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)


def test_a_remark_on_an_otherwise_empty_response_raises_instead_of_zero() -> None:
    """빈 elements + remark 는 "0개 발견"이 아니라 서버 타임아웃 등의 실패다."""

    def transport(url: str, body: bytes) -> bytes:
        return json.dumps(
            {"elements": [], "remark": "runtime error: Query timed out"}
        ).encode()

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    source = OverpassParkSource(client)

    with pytest.raises(OverpassFetchError, match="Query timed out"):
        source.polygons_near(QUERY_LAT, QUERY_LON, radius_m=800.0)
