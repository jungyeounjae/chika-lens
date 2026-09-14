"""SUUMO 신축 분양 목록 페이지 파싱 — HTTP 도, 지오코딩도 하지 않는다.

셀렉터는 전부 실측이다(2026-09-14, `sc_shinjuku/`·`sc_setagaya/` 실제 DOM).
마크업이 바뀌면 조용히 0건으로 접지 않고 SuumoShapeError 를 던진다 —
mlit_prices.py::TransactionShapeError 와 같은 이유: 결측으로 접으면
사이트 개편을 몇 달 뒤에야 알아챈다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class SuumoShapeError(RuntimeError):
    """SUUMO 마크업이 예상과 다르다."""


@dataclass(frozen=True)
class NewConstructionListing:
    """신축 물건 하나. lat/lon 은 아직 지오코딩 전이라 None 일 수 있다."""

    suumo_id: str
    name: str
    ward: str
    address_raw: str
    lat: float | None
    lon: float | None
    price_min_yen: int | None
    price_max_yen: int | None
    floor_area_min_sqm: float | None
    floor_area_max_sqm: float | None
    delivery_period_raw: str
    url: str
    fetched_at: str


_YEN_PATTERN = re.compile(r"(?:(\d+)億)?(?:(\d+)万)?円")
_AREA_PATTERN = re.compile(r"([\d.]+)m")
_PAGE_PATTERN = re.compile(r"\?page=(\d+)")
_ID_PATTERN = re.compile(r"nc_(\d+)")


def _parse_yen(text: str) -> int:
    match = _YEN_PATTERN.search(text)
    if not match or (match.group(1) is None and match.group(2) is None):
        raise SuumoShapeError(f"금액 포맷이 아니다: {text!r}")
    oku = int(match.group(1) or 0)
    man = int(match.group(2) or 0)
    return oku * 100_000_000 + man * 10_000


def parse_price_range(text: str) -> tuple[int | None, int | None]:
    """"9890万円～1億7290万円" -> (98900000, 172900000). "価格未定" -> (None, None)."""
    text = text.strip()
    if "円" not in text:
        return None, None
    parts = text.split("～")
    if len(parts) == 1:
        price = _parse_yen(parts[0])
        return price, price
    return _parse_yen(parts[0]), _parse_yen(parts[1])


def parse_area_range(text: str) -> tuple[float | None, float | None]:
    """"2LDK・3LDK / 55.08m2～76.56m2" -> (55.08, 76.56). 간형이 하나뿐이면 둘 다 같은 값."""
    area_part = text.rsplit("/", 1)[-1]
    numbers = _AREA_PATTERN.findall(area_part)
    if not numbers:
        return None, None
    if len(numbers) == 1:
        value = float(numbers[0])
        return value, value
    return float(numbers[0]), float(numbers[-1])


def max_page_number(html: str) -> int:
    """페이지네이션에 있는 가장 큰 page 번호. 페이지네이션이 없으면(=1페이지 뿐) 1."""
    numbers = [int(n) for n in _PAGE_PATTERN.findall(html)]
    return max(numbers, default=1)


def parse_listing_page(
    html: str, ward: str, base_url: str = "https://suumo.jp"
) -> list[NewConstructionListing]:
    """물건 목록 페이지 하나(=`?page=N` 한 장)를 파싱한다. 0건은 유효한 결과다 —
    호출부(build_new_construction.py)가 구 전체 합계를 보고 이상을 판단한다."""
    soup = BeautifulSoup(html, "html.parser")
    today = dt.date.today().isoformat()
    listings: list[NewConstructionListing] = []

    for cassette in soup.select(".property_unit"):
        title_tag = cassette.select_one(".cassette_header-title")
        href = title_tag.get("href") if title_tag else None
        if not title_tag or not href or not isinstance(href, str):
            raise SuumoShapeError(
                "물건 제목/링크(.cassette_header-title)를 찾지 못했다 — "
                "SUUMO 마크업이 바뀌었을 수 있다"
            )
        url = urljoin(base_url, href)
        id_match = _ID_PATTERN.search(url)
        if id_match is None:
            raise SuumoShapeError(f"URL 에서 물건 id(nc_숫자)를 못 찾았다: {url!r}")

        basics: dict[str, str] = {}
        for item in cassette.select(".cassette_basic-list_item"):
            label = item.select_one(".cassette_basic-title")
            value = item.select_one(".cassette_basic-value")
            if label is not None and value is not None:
                basics[label.get_text(strip=True)] = value.get_text(strip=True)

        price_tag = cassette.select_one(".cassette_price-accent")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        price_min, price_max = parse_price_range(price_text)

        description_tag = cassette.select_one(".cassette_price-description")
        area_min, area_max = parse_area_range(
            description_tag.get_text(strip=True) if description_tag else ""
        )

        listings.append(
            NewConstructionListing(
                suumo_id=id_match.group(1),
                name=title_tag.get_text(strip=True),
                ward=ward,
                address_raw=basics.get("所在地", ""),
                lat=None,
                lon=None,
                price_min_yen=price_min,
                price_max_yen=price_max,
                floor_area_min_sqm=area_min,
                floor_area_max_sqm=area_max,
                delivery_period_raw=basics.get("引渡時期", ""),
                url=url,
                fetched_at=today,
            )
        )
    return listings
