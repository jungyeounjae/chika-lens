"""23구 슬러그 매핑 — 개수와 형태만 지킨다(값 자체는 실측 상수)."""

from __future__ import annotations

from chika.etl.suumo_wards import TOKYO_23_WARDS


def test_all_23_wards_are_present() -> None:
    assert len(TOKYO_23_WARDS) == 23


def test_every_ward_name_ends_with_ku() -> None:
    assert all(ward.endswith("区") for ward in TOKYO_23_WARDS)


def test_every_slug_is_lowercase_ascii() -> None:
    assert all(slug.isascii() and slug.islower() for slug in TOKYO_23_WARDS.values())


def test_shinjuku_maps_to_its_real_suumo_slug() -> None:
    """실측(2026-09-14, https://suumo.jp/ms/shinchiku/tokyo/) 값 하나를 고정으로."""
    assert TOKYO_23_WARDS["新宿区"] == "shinjuku"
