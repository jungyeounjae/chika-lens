"""SchoolFacility 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.facility import SchoolFacility


def test_a_facility_can_be_constructed_with_all_fields() -> None:
    facility = SchoolFacility(
        facility_id="f_12345",
        name="光が丘第八小学校",
        kind="小学校",
        lat=35.7601,
        lon=139.6089,
        distance_m=312.4,
    )
    assert facility.name == "光が丘第八小学校"
    assert facility.kind == "小学校"
    assert facility.distance_m == 312.4
