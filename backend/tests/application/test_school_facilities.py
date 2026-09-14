"""SchoolFacilities 유스케이스 — 포트(SchoolFacilitySource)에 위임할 뿐임을 확인한다."""

from __future__ import annotations

from chika.application.usecase.school_facilities import SchoolFacilities
from chika.domain.model.facility import SchoolFacility


class _StubSource:
    def __init__(self, facilities: list[SchoolFacility]) -> None:
        self._facilities = facilities
        self.calls: list[tuple[float, float, float]] = []

    def facilities_near(self, lat: float, lon: float, radius_m: float) -> list[SchoolFacility]:
        self.calls.append((lat, lon, radius_m))
        return self._facilities


def test_execute_forwards_coordinates_and_radius_to_the_source() -> None:
    source = _StubSource([])
    usecase = SchoolFacilities(source)

    usecase.execute(35.76, 139.61, radius_m=900.0)

    assert source.calls == [(35.76, 139.61, 900.0)]


def test_execute_uses_800m_as_the_default_radius() -> None:
    source = _StubSource([])
    usecase = SchoolFacilities(source)

    usecase.execute(35.76, 139.61)

    assert source.calls == [(35.76, 139.61, 800.0)]


def test_execute_returns_the_sources_facilities() -> None:
    facility = SchoolFacility(
        facility_id="f1", name="光が丘第八小学校", kind="小学校",
        lat=35.76, lon=139.61, distance_m=120.0,
    )
    usecase = SchoolFacilities(_StubSource([facility]))

    result = usecase.execute(35.76, 139.61)

    assert result == [facility]
