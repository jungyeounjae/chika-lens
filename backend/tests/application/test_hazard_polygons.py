"""HazardPolygons 유스케이스 — 포트(HazardPolygonSource)에 위임할 뿐임을 확인한다."""

from __future__ import annotations

import pytest

from chika.application.usecase.hazard_polygons import HazardPolygons
from chika.domain.model.polygon import HazardPolygon
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


class _StubSource:
    def __init__(self, polygons: list[HazardPolygon]) -> None:
        self._polygons = polygons
        self.calls: list[tuple[float, float, float]] = []

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[HazardPolygon]:
        self.calls.append((lat, lon, radius_m))
        return self._polygons


def _station(station_id: str) -> Station:
    return Station(id=station_id, name_ja=station_id, ward="中野区", lat=35.7, lon=139.6, lines=())


def test_execute_looks_up_the_station_and_forwards_its_coordinates() -> None:
    areas = FakeAreaMetricsRepository([_station("a")], [])
    source = _StubSource([])
    usecase = HazardPolygons(areas, source)

    usecase.execute("a", radius_m=900.0)

    assert source.calls == [(35.7, 139.6, 900.0)]


def test_execute_returns_the_station_and_the_sources_polygons() -> None:
    areas = FakeAreaMetricsRepository([_station("a")], [])
    polygon = HazardPolygon(
        layer="flood",
        geometry={"type": "Polygon", "coordinates": []},
        severity=0.5,
        label="0.5m~3.0m",
    )
    usecase = HazardPolygons(areas, _StubSource([polygon]))

    station, polygons = usecase.execute("a")

    assert station.id == "a"
    assert polygons == [polygon]


def test_an_unknown_station_raises_key_error() -> None:
    areas = FakeAreaMetricsRepository([_station("a")], [])
    usecase = HazardPolygons(areas, _StubSource([]))

    with pytest.raises(KeyError):
        usecase.execute("not_a_station")
