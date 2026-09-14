"""신축 분양 마스터 배치 — SUUMO(도쿄 23구) 크롤링 + GSI 지오코딩.

MLIT API 는 공공데이터라 '현재 마케팅 중인 신축 분양가·모델하우스 일정'을
주지 않는다(실거래는 준공 후에나 잡힌다) — 그래서 이 배치만 외부 포털을
직접 크롤링한다. robots.txt 확인(2026-09-14): `/ms/shinchiku/tokyo/sc_*/`
계열은 불허 목록에 없다. 요청 간격 2초 이상으로 개인 용도 수준을 지킨다.

사용법:

    uv run python -m chika.etl.build_new_construction
    uv run python -m chika.etl.build_new_construction --wards shinjuku,shibuya
    uv run python -m chika.etl.build_new_construction --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chika.etl.gsi_geocoder import GeocodeFetchError, GsiGeocoder
from chika.etl.suumo_client import SuumoClient, SuumoFetchError
from chika.etl.suumo_new_construction import (
    NewConstructionListing,
    max_page_number,
    parse_listing_page,
)
from chika.etl.suumo_wards import TOKYO_23_WARDS

# station.py 의 TOKYO_BBOX 와 동일한 범위를 미러링한다 — domain 계층을 etl 에서
# import 하지 않는다는 아키텍처 방침 때문에 여기서 별도로 정의한다.
_TOKYO_BBOX = (35.50, 35.85, 139.55, 139.95)  # lat_min, lat_max, lon_min, lon_max


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/new_construction.json"))
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("data/.cache/suumo_new_construction")
    )
    parser.add_argument(
        "--geocode-cache", type=Path, default=Path("data/.cache/geocode_cache.json")
    )
    parser.add_argument(
        "--wards", help="쉼표로 구분한 구 슬러그(예: shinjuku,shibuya). 생략하면 23구 전체."
    )
    parser.add_argument("--refresh", action="store_true", help="HTML 캐시를 무시하고 재수집")
    args = parser.parse_args()

    wards = _selected_wards(args.wards)
    client = SuumoClient()
    listings = _crawl_all_wards(client, wards, args.cache_dir, args.refresh)
    print(f"물건 {len(listings)}건 수집 (구 {len(wards)}개)")

    geocode_cache = _load_geocode_cache(args.geocode_cache, args.refresh)
    geocoder = GsiGeocoder()
    geocoded = _geocode_all(listings, geocoder, geocode_cache)
    args.geocode_cache.parent.mkdir(parents=True, exist_ok=True)
    args.geocode_cache.write_text(
        json.dumps(geocode_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    missing = [item for item in geocoded if item.lat is None]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([_to_dict(item) for item in geocoded], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{args.out} 에 {len(geocoded)}건 기록 (지오코딩 결측 {len(missing)}건)")
    if missing:
        print("  결측:", ", ".join(f"{m.name}({m.address_raw})" for m in missing[:10]))


def _selected_wards(raw: str | None) -> dict[str, str]:
    if raw is None:
        return TOKYO_23_WARDS
    slugs = {s.strip() for s in raw.split(",") if s.strip()}
    by_slug = {slug: ward for ward, slug in TOKYO_23_WARDS.items()}
    unknown = slugs - set(by_slug)
    if unknown:
        sys.exit(f"모르는 구 슬러그: {sorted(unknown)}")
    return {by_slug[slug]: slug for slug in slugs}


def _crawl_all_wards(
    client: SuumoClient, wards: dict[str, str], cache_dir: Path, refresh: bool
) -> list[NewConstructionListing]:
    listings: list[NewConstructionListing] = []
    for ward, slug in wards.items():
        ward_listings = _crawl_ward(client, ward, slug, cache_dir, refresh)
        print(f"  {ward}: {len(ward_listings)}건")
        if not ward_listings:
            print(f"    경고: {ward} 물건이 0건이다 — 마크업이 바뀌었을 수 있다")
        listings.extend(ward_listings)
    return listings


def _crawl_ward(
    client: SuumoClient, ward: str, slug: str, cache_dir: Path, refresh: bool
) -> list[NewConstructionListing]:
    base_url = f"https://suumo.jp/ms/shinchiku/tokyo/sc_{slug}/"
    first_html = _fetch_cached(client, base_url, cache_dir / f"{slug}_1.html", refresh)
    pages = max_page_number(first_html)

    listings = list(parse_listing_page(first_html, ward))
    for page in range(2, pages + 1):
        page_url = f"{base_url}?page={page}"
        html = _fetch_cached(client, page_url, cache_dir / f"{slug}_{page}.html", refresh)
        listings.extend(parse_listing_page(html, ward))
    return listings


def _fetch_cached(client: SuumoClient, url: str, cache_path: Path, refresh: bool) -> str:
    if not refresh and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    try:
        html = client.fetch_html(url)
    except SuumoFetchError as exc:
        sys.exit(f"중단: {exc}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


def _load_geocode_cache(path: Path, refresh: bool = False) -> dict[str, list[float] | None]:
    if refresh or not path.exists():
        return {}
    loaded: dict[str, list[float] | None] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _in_tokyo_bbox(coords: tuple[float, float]) -> bool:
    lat, lon = coords
    lat_min, lat_max, lon_min, lon_max = _TOKYO_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _geocode_all(
    listings: list[NewConstructionListing],
    geocoder: GsiGeocoder,
    cache: dict[str, list[float] | None],
) -> list[NewConstructionListing]:
    result: list[NewConstructionListing] = []
    for listing in listings:
        key = f"{listing.ward}{listing.address_raw}"
        if key not in cache:
            address = (
                listing.address_raw
                if listing.address_raw.startswith("東京都")
                else f"東京都{listing.address_raw}"
            )
            coords: tuple[float, float] | None = None
            if address.strip() != "東京都":
                try:
                    coords = geocoder.geocode(address)
                except GeocodeFetchError as exc:
                    print(f"    지오코딩 실패, 결측으로 남긴다: {key} ({exc})")
                    coords = None
                if coords is not None and not _in_tokyo_bbox(coords):
                    print(f"    도쿄 범위 밖 좌표, 결측으로 남긴다: {key} ({coords})")
                    coords = None
            cache[key] = list(coords) if coords else None
        cached_coords = cache[key]
        lat, lon = (cached_coords[0], cached_coords[1]) if cached_coords else (None, None)
        result.append(
            NewConstructionListing(
                suumo_id=listing.suumo_id,
                name=listing.name,
                ward=listing.ward,
                address_raw=listing.address_raw,
                lat=lat,
                lon=lon,
                price_min_yen=listing.price_min_yen,
                price_max_yen=listing.price_max_yen,
                floor_area_min_sqm=listing.floor_area_min_sqm,
                floor_area_max_sqm=listing.floor_area_max_sqm,
                delivery_period_raw=listing.delivery_period_raw,
                url=listing.url,
                fetched_at=listing.fetched_at,
            )
        )
    return result


def _to_dict(listing: NewConstructionListing) -> dict[str, object]:
    return {
        "suumo_id": listing.suumo_id,
        "name": listing.name,
        "ward": listing.ward,
        "address_raw": listing.address_raw,
        "lat": listing.lat,
        "lon": listing.lon,
        "price_min_yen": listing.price_min_yen,
        "price_max_yen": listing.price_max_yen,
        "floor_area_min_sqm": listing.floor_area_min_sqm,
        "floor_area_max_sqm": listing.floor_area_max_sqm,
        "delivery_period_raw": listing.delivery_period_raw,
        "url": listing.url,
        "fetched_at": listing.fetched_at,
    }


if __name__ == "__main__":
    main()
