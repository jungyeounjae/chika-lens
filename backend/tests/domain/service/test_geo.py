"""역 간 거리 — 지도에 주변 역을 표시하기 위한 순수 계산. API를 부르지 않는다."""

import pytest

from chika.domain.service.geo import distance_meters

NAKANO = (35.7057, 139.6656)
SHINJUKU = (35.6900, 139.6992)


def test_distance_to_itself_is_zero() -> None:
    assert distance_meters(*NAKANO, *NAKANO) == pytest.approx(0.0)


def test_nakano_to_shinjuku_is_about_3_5km() -> None:
    """실측 약 3.4km. 하버사인이 도쿄 위도에서 맞는지 확인한다."""
    assert distance_meters(*NAKANO, *SHINJUKU) == pytest.approx(3400, abs=200)


def test_distance_is_symmetric() -> None:
    forward = distance_meters(*NAKANO, *SHINJUKU)
    backward = distance_meters(*SHINJUKU, *NAKANO)
    assert forward == pytest.approx(backward)


def test_a_small_longitude_step_shrinks_with_latitude() -> None:
    """경도 1도는 적도에서 111km, 도쿄(북위 35도)에서는 약 90km다."""
    at_tokyo = distance_meters(35.7, 139.0, 35.7, 140.0)
    at_equator = distance_meters(0.0, 139.0, 0.0, 140.0)
    assert at_tokyo < at_equator
    assert at_tokyo == pytest.approx(90_000, abs=3_000)
