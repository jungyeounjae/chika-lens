"""신축 물건 도메인 모델 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)


def test_a_listing_can_be_constructed_with_all_fields_present() -> None:
    listing = NewConstructionListing(
        suumo_id="67733465",
        name="リビオ高田馬場",
        ward="新宿区",
        address_raw="新宿区下落合１",
        lat=35.71574,
        lon=139.699585,
        price_min_yen=98_900_000,
        price_max_yen=172_900_000,
        floor_area_min_sqm=55.08,
        floor_area_max_sqm=76.56,
        delivery_period_raw="2027年4月下旬予定",
        url="https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/",
        fetched_at="2026-09-14",
        hazard_summary={"flood": HazardLevel(severity=0.667, label="5.0m~10.0m")},
        quietness=NewConstructionQuietness(
            station_id="st_844aa570351c",
            station_name="下落合",
            distance_m=387.8,
            daily_ridership=11361.0,
        ),
    )
    assert listing.hazard_summary["flood"].label == "5.0m~10.0m"
    assert listing.quietness is not None
    assert listing.quietness.daily_ridership == 11361.0


def test_a_listing_can_have_missing_coordinates_and_quietness() -> None:
    """지오코딩 결측·역 매칭 실패도 유효한 상태다 — None 허용."""
    listing = NewConstructionListing(
        suumo_id="1",
        name="테스트",
        ward="新宿区",
        address_raw="新宿区",
        lat=None,
        lon=None,
        price_min_yen=None,
        price_max_yen=None,
        floor_area_min_sqm=None,
        floor_area_max_sqm=None,
        delivery_period_raw="",
        url="",
        fetched_at="2026-09-14",
        hazard_summary={},
        quietness=None,
    )
    assert listing.lat is None
    assert listing.quietness is None
    assert listing.hazard_summary == {}
