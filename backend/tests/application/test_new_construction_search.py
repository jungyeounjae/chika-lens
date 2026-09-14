"""NewConstructionSearch — 구/가격대/재해위험/정숙도 필터 + find_by_id."""

from __future__ import annotations

from chika.application.usecase.new_construction_search import (
    NewConstructionFilter,
    NewConstructionSearch,
)
from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)


def _listing(
    suumo_id: str,
    ward: str = "新宿区",
    price_min_yen: int | None = 50_000_000,
    price_max_yen: int | None = 60_000_000,
    hazard_summary: dict[str, HazardLevel] | None = None,
    daily_ridership: float | None = 10_000.0,
) -> NewConstructionListing:
    return NewConstructionListing(
        suumo_id=suumo_id,
        name=f"物件{suumo_id}",
        ward=ward,
        address_raw="",
        lat=35.7,
        lon=139.7,
        price_min_yen=price_min_yen,
        price_max_yen=price_max_yen,
        floor_area_min_sqm=None,
        floor_area_max_sqm=None,
        delivery_period_raw="",
        url="",
        fetched_at="2026-09-14",
        hazard_summary=hazard_summary or {},
        quietness=NewConstructionQuietness(
            station_id="st_x", station_name="X", distance_m=300.0,
            daily_ridership=daily_ridership,
        ),
    )


class _FakeRepo:
    def __init__(self, listings: list[NewConstructionListing]) -> None:
        self._listings = listings

    def listings(self) -> list[NewConstructionListing]:
        return self._listings


def test_filters_by_ward() -> None:
    repo = _FakeRepo([_listing("1", ward="新宿区"), _listing("2", ward="渋谷区")])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(ward="渋谷区"))

    assert [item.suumo_id for item in result] == ["2"]


def test_excludes_listings_with_unknown_price_when_a_price_filter_is_active() -> None:
    repo = _FakeRepo(
        [
            _listing("1", price_min_yen=50_000_000, price_max_yen=60_000_000),
            _listing("2", price_min_yen=None, price_max_yen=None),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(max_price_yen=100_000_000))

    assert [item.suumo_id for item in result] == ["1"]


def test_no_price_filter_includes_listings_with_unknown_price() -> None:
    repo = _FakeRepo([_listing("1", price_min_yen=None, price_max_yen=None)])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter())

    assert [item.suumo_id for item in result] == ["1"]


def test_excludes_listings_whose_worst_hazard_severity_exceeds_the_threshold() -> None:
    repo = _FakeRepo(
        [
            _listing("safe", hazard_summary={"flood": HazardLevel(severity=0.2, label="x")}),
            _listing("risky", hazard_summary={"flood": HazardLevel(severity=0.9, label="y")}),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(max_hazard_severity=0.5))

    assert [item.suumo_id for item in result] == ["safe"]


def test_filters_by_ridership_range() -> None:
    repo = _FakeRepo(
        [
            _listing("quiet", daily_ridership=2_000.0),
            _listing("busy", daily_ridership=90_000.0),
        ]
    )
    search = NewConstructionSearch(repo)

    quiet_only = search.execute(NewConstructionFilter(max_daily_ridership=5_000.0))
    busy_only = search.execute(NewConstructionFilter(min_daily_ridership=50_000.0))

    assert [item.suumo_id for item in quiet_only] == ["quiet"]
    assert [item.suumo_id for item in busy_only] == ["busy"]


def test_results_are_sorted_by_price_ascending_with_unknown_price_last() -> None:
    repo = _FakeRepo(
        [
            _listing("expensive", price_min_yen=200_000_000),
            _listing("unknown", price_min_yen=None),
            _listing("cheap", price_min_yen=50_000_000),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter())

    assert [item.suumo_id for item in result] == ["cheap", "expensive", "unknown"]


def test_limit_caps_the_result_count() -> None:
    repo = _FakeRepo([_listing(str(i)) for i in range(5)])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(), limit=2)

    assert len(result) == 2


def test_find_by_id_returns_none_when_not_found() -> None:
    repo = _FakeRepo([_listing("1")])
    search = NewConstructionSearch(repo)

    assert search.find_by_id("does-not-exist") is None
    assert search.find_by_id("1") is not None
