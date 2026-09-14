"""좌표 -> 최근접 역 + 그 역의 승하차인원(정숙도 프록시)."""

from __future__ import annotations

from chika.domain.model.station import Station
from chika.etl.new_construction_quietness import nearest_quietness

_SHINJUKU = Station(
    id="st_shinjuku",
    name_ja="新宿",
    ward="新宿区",
    lat=35.6896,
    lon=139.7006,
    lines=("JR山手線",),
)
_TAKADANOBABA = Station(
    id="st_takada",
    name_ja="高田馬場",
    ward="新宿区",
    lat=35.7127,
    lon=139.7038,
    lines=("JR山手線",),
)


def test_the_nearer_station_by_straight_line_distance_wins() -> None:
    # 신주쿠역과 거의 같은 좌표 -> 신주쿠가 최근접.
    result = nearest_quietness(
        35.6897, 139.7007, [_SHINJUKU, _TAKADANOBABA], {"st_shinjuku": 500_000.0}
    )
    assert result is not None
    assert result.station_id == "st_shinjuku"
    assert result.station_name == "新宿"
    assert result.distance_m < 100
    assert result.daily_ridership == 500_000.0


def test_a_station_missing_from_the_ridership_index_reports_missing_not_zero() -> None:
    """배치가 아직 안 돈 역이나 표본 부족으로 결측인 역이 있을 수 있다(스펙
    §MIN_SAMPLES) — 0으로 채우면 '한산한 역'과 '모르는 역'을 혼동한다."""
    result = nearest_quietness(35.6897, 139.7007, [_SHINJUKU], {})
    assert result is not None
    assert result.daily_ridership is None


def test_no_stations_at_all_returns_none() -> None:
    assert nearest_quietness(35.6897, 139.7007, [], {}) is None
