"""ParkPolygon 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.polygon import ParkPolygon


def test_a_park_polygon_can_be_constructed_with_a_name() -> None:
    polygon = ParkPolygon(
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [139.6, 35.76],
                    [139.61, 35.76],
                    [139.61, 35.77],
                    [139.6, 35.77],
                    [139.6, 35.76],
                ]
            ],
        },
        name="北原公園",
    )
    assert polygon.name == "北原公園"
    assert polygon.geometry["type"] == "Polygon"


def test_a_park_polygon_can_have_a_missing_name() -> None:
    """OSM 에 이름이 없는 공원도 실측에서 나왔다 — None 허용, 지어내지 않는다."""
    polygon = ParkPolygon(geometry={"type": "Polygon", "coordinates": []}, name=None)
    assert polygon.name is None
