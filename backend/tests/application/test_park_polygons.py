"""ParkPolygons 유스케이스 — 포트(ParkPolygonSource)에 위임할 뿐임을 확인한다."""

from __future__ import annotations

from chika.application.usecase.park_polygons import ParkPolygons
from chika.domain.model.polygon import ParkPolygon


class _StubSource:
    def __init__(self, polygons: list[ParkPolygon]) -> None:
        self._polygons = polygons
        self.calls: list[tuple[float, float, float]] = []

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[ParkPolygon]:
        self.calls.append((lat, lon, radius_m))
        return self._polygons


def test_execute_forwards_coordinates_and_radius_to_the_source() -> None:
    source = _StubSource([])
    usecase = ParkPolygons(source)

    usecase.execute(35.76, 139.61, radius_m=900.0)

    assert source.calls == [(35.76, 139.61, 900.0)]


def test_execute_uses_800m_as_the_default_radius() -> None:
    source = _StubSource([])
    usecase = ParkPolygons(source)

    usecase.execute(35.76, 139.61)

    assert source.calls == [(35.76, 139.61, 800.0)]


def test_execute_returns_the_sources_polygons() -> None:
    polygon = ParkPolygon(geometry={"type": "Polygon", "coordinates": []}, name="北原公園")
    usecase = ParkPolygons(_StubSource([polygon]))

    result = usecase.execute(35.76, 139.61)

    assert result == [polygon]
