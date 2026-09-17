"""LandmarkMatch 값 객체 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.landmark import LandmarkMatch


def test_a_landmark_match_can_be_constructed() -> None:
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    assert match.name == "新宿御苑"
    assert match.lat == 35.6851
    assert match.lon == 139.7095
