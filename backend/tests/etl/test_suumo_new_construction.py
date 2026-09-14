"""SUUMO 물건 카드 파싱 — 실측 HTML(2026-09-14, sc_shinjuku/) 을 축약한 픽스처."""

from __future__ import annotations

import pytest

from chika.etl.suumo_new_construction import (
    SuumoShapeError,
    max_page_number,
    parse_area_range,
    parse_listing_page,
    parse_price_range,
)

# 실측: https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/ 의 "リビオ高田馬場" 카드.
LISTING_WITH_PRICE = (
    '<div class="cassette property_unit">'
    '  <div class="cassette-content">'
    '    <div class="cassette_header">'
    '      <h2><a href="/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/"'
    '        class="cassette_header-title">リビオ高田馬場</a></h2>'
    "    </div>"
    '    <div class="cassette-result_detail">'
    '      <div class="cassette_basic">'
    "        <ul class=\"cassette_basic-list\">"
    '          <li class="cassette_basic-list_item">'
    '            <div class="cassette_basic-item">'
    '              <p class="cassette_basic-title">所在地</p>'
    '              <p class="cassette_basic-value">新宿区下落合１</p>'
    "            </div>"
    "          </li>"
    '          <li class="cassette_basic-list_item">'
    '            <div class="cassette_basic-item">'
    '              <p class="cassette_basic-title">引渡時期</p>'
    '              <p class="cassette_basic-value">2027年4月下旬予定</p>'
    "            </div>"
    "          </li>"
    "        </ul>"
    "      </div>"
    '      <div class="cassette_price cassette_price--layout">'
    "        <ul class=\"cassette_price-list\">"
    '          <li class="cassette_price-list_item">'
    '            <div class="cassette_price-value">'
    '              <span class="cassette_price-accent">9890万円～1億7290万円</span>'
    "            </div>"
    "            <p class=\"cassette_price-description\">2LDK・3LDK / 55.08m<sup>2</sup>"
    "～76.56m<sup>2</sup></p>"
    "          </li>"
    "        </ul>"
    "      </div>"
    "    </div>"
    "  </div>"
    "</div>"
)

# 실측: 같은 페이지의 "ジオ飯田橋" 카드 — 가격 미정.
LISTING_PRICE_UNDECIDED = (
    '<div class="cassette property_unit">'
    '  <div class="cassette-content">'
    '    <div class="cassette_header">'
    '      <h2><a href="/ms/shinchiku/tokyo/sc_shinjuku/nc_67735307/"'
    '        class="cassette_header-title">ジオ飯田橋</a></h2>'
    "    </div>"
    '    <div class="cassette-result_detail">'
    '      <div class="cassette_basic">'
    "        <ul class=\"cassette_basic-list\">"
    '          <li class="cassette_basic-list_item">'
    '            <div class="cassette_basic-item">'
    '              <p class="cassette_basic-title">所在地</p>'
    '              <p class="cassette_basic-value">新宿区新小川町</p>'
    "            </div>"
    "          </li>"
    "        </ul>"
    "      </div>"
    '      <div class="cassette_price cassette_price--layout">'
    "        <ul class=\"cassette_price-list\">"
    '          <li class="cassette_price-list_item">'
    '            <div class="cassette_price-value">'
    '              <span class="cassette_price-accent">価格未定</span>'
    "            </div>"
    "            <p class=\"cassette_price-description\">1LDK～3LDK / 43.94m<sup>2</sup>"
    "～151.39m<sup>2</sup></p>"
    "          </li>"
    "        </ul>"
    "      </div>"
    "    </div>"
    "  </div>"
    "</div>"
)

# 실측: https://suumo.jp/ms/shinchiku/tokyo/sc_setagaya/ (33건 -> 2페이지).
PAGINATION_TWO_PAGES = (
    '<div class="sortbox_pagination">'
    '<ol class="sortbox_pagination-parts">'
    '<li class="sortbox_pagination-list sortbox_pagination--current">1</li>'
    "<li>&nbsp;</li>"
    '<li class="sortbox_pagination-list"><a class="sortbox_pagination-link"'
    ' href="/ms/shinchiku/tokyo/sc_setagaya/?page=2">2</a></li>'
    "</ol>"
    "</div>"
)


def test_a_price_range_is_parsed_to_yen() -> None:
    assert parse_price_range("9890万円～1億7290万円") == (98_900_000, 172_900_000)


def test_an_undecided_price_is_missing_not_zero() -> None:
    assert parse_price_range("価格未定") == (None, None)


def test_a_single_price_without_a_range_is_both_min_and_max() -> None:
    assert parse_price_range("1億2490万円") == (124_900_000, 124_900_000)


def test_an_area_range_is_parsed_to_sqm() -> None:
    assert parse_area_range("2LDK・3LDK / 55.08m2～76.56m2") == (55.08, 76.56)


def test_max_page_number_reads_the_pagination_links() -> None:
    assert max_page_number(PAGINATION_TWO_PAGES) == 2


def test_a_single_page_ward_has_no_pagination_links() -> None:
    assert max_page_number("<div>물건 23건, 페이지네이션 없음</div>") == 1


def test_max_page_number_matches_page_after_other_query_params() -> None:
    """실제 구 목록 페이지네이션은 `?cn=...&page=N` 형태로 다른 파라미터 뒤에 온다."""
    html = (
        '<a href="/ms/shinchiku/tokyo/sc_chiyoda/?cn=9999999&page=3">3</a>'
    )
    assert max_page_number(html) == 3


def test_parsing_a_listing_with_a_price_range() -> None:
    listings = parse_listing_page(LISTING_WITH_PRICE, ward="新宿区")
    assert len(listings) == 1
    listing = listings[0]
    assert listing.suumo_id == "67733465"
    assert listing.name == "リビオ高田馬場"
    assert listing.ward == "新宿区"
    assert listing.address_raw == "新宿区下落合１"
    assert listing.price_min_yen == 98_900_000
    assert listing.price_max_yen == 172_900_000
    assert listing.floor_area_min_sqm == 55.08
    assert listing.floor_area_max_sqm == 76.56
    assert listing.delivery_period_raw == "2027年4月下旬予定"
    assert listing.url == "https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/"
    assert listing.lat is None and listing.lon is None  # 지오코딩 전 단계


def test_parsing_a_listing_with_an_undecided_price() -> None:
    listings = parse_listing_page(LISTING_PRICE_UNDECIDED, ward="新宿区")
    assert listings[0].price_min_yen is None
    assert listings[0].price_max_yen is None
    assert listings[0].floor_area_min_sqm == 43.94
    assert listings[0].floor_area_max_sqm == 151.39


def test_a_page_with_no_cards_returns_an_empty_list() -> None:
    """물건 0건인 구가 실제로 있을 수 있다 — 빈 리스트는 유효한 답이다."""
    assert parse_listing_page("<div>no cards here</div>", ward="千代田区") == []


def test_a_card_missing_its_title_link_raises_instead_of_silently_skipping() -> None:
    broken = '<div class="cassette property_unit"><p>제목 없음</p></div>'
    with pytest.raises(SuumoShapeError):
        parse_listing_page(broken, ward="新宿区")
