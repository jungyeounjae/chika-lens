"""FileNewConstructionRepository — data/new_construction_enriched.json 형태 파싱."""

from __future__ import annotations

import json
from pathlib import Path

from chika.infrastructure.file_new_construction import FileNewConstructionRepository


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "new_construction_enriched.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_full_listing_is_parsed_with_hazard_and_quietness(tmp_path: Path) -> None:
    rows = [
        {
            "suumo_id": "67733465",
            "name": "リビオ高田馬場",
            "ward": "新宿区",
            "address_raw": "新宿区下落合１",
            "lat": 35.71574,
            "lon": 139.699585,
            "price_min_yen": 98_900_000,
            "price_max_yen": 172_900_000,
            "floor_area_min_sqm": 55.08,
            "floor_area_max_sqm": 76.56,
            "delivery_period_raw": "2027年4月下旬予定",
            "url": "https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/",
            "fetched_at": "2026-09-14",
            "hazard_summary": {
                "flood": {"severity": 0.6666666666666666, "label": "5.0m~10.0m"},
                "sediment": {"severity": 1.0, "label": "레드존(급경사지 붕괴위험, 지정완료)"},
            },
            "quietness": {
                "station_id": "st_844aa570351c",
                "station_name": "下落合",
                "distance_m": 387.8,
                "daily_ridership": 11361.0,
            },
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listings = repo.listings()

    assert len(listings) == 1
    listing = listings[0]
    assert listing.suumo_id == "67733465"
    assert listing.hazard_summary["flood"].label == "5.0m~10.0m"
    assert listing.hazard_summary["sediment"].severity == 1.0
    assert listing.quietness is not None
    assert listing.quietness.station_name == "下落合"
    assert listing.quietness.daily_ridership == 11361.0


def test_a_listing_with_no_coordinates_and_no_quietness_match(tmp_path: Path) -> None:
    rows = [
        {
            "suumo_id": "2",
            "name": "테스트",
            "ward": "新宿区",
            "address_raw": "新宿区",
            "lat": None,
            "lon": None,
            "price_min_yen": None,
            "price_max_yen": None,
            "floor_area_min_sqm": None,
            "floor_area_max_sqm": None,
            "delivery_period_raw": "",
            "url": "",
            "fetched_at": "2026-09-14",
            "hazard_summary": {},
            "quietness": None,
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listing = repo.listings()[0]

    assert listing.lat is None
    assert listing.quietness is None
    assert listing.hazard_summary == {}


def test_a_quietness_with_missing_ridership_stays_none(tmp_path: Path) -> None:
    """정숙도 매칭은 됐지만 승하차인원 자체가 결측인 경우(표본 부족 등)."""
    rows = [
        {
            "suumo_id": "3",
            "name": "테스트",
            "ward": "新宿区",
            "address_raw": "新宿区",
            "lat": 35.7,
            "lon": 139.7,
            "price_min_yen": None,
            "price_max_yen": None,
            "floor_area_min_sqm": None,
            "floor_area_max_sqm": None,
            "delivery_period_raw": "",
            "url": "",
            "fetched_at": "2026-09-14",
            "hazard_summary": {},
            "quietness": {
                "station_id": "st_x",
                "station_name": "テスト駅",
                "distance_m": 500.0,
                "daily_ridership": None,
            },
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listing = repo.listings()[0]

    assert listing.quietness is not None
    assert listing.quietness.daily_ridership is None


def test_a_missing_file_returns_an_empty_list_not_an_error(tmp_path: Path) -> None:
    """아직 그 구를 크롤링/결합 배치를 안 돌렸을 수 있다 — 세션이 죽으면 안 된다."""
    repo = FileNewConstructionRepository(tmp_path / "does_not_exist.json")

    assert repo.listings() == []
