"""ensure_ward_crawled — 구 단위 lazy 크롤링의 분기(네트워크는 타지 않는다)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chika.etl import lazy_new_construction
from chika.etl.lazy_new_construction import _merge_by_suumo_id, ensure_ward_crawled


def test_an_unknown_ward_does_nothing(tmp_path: Path) -> None:
    """SUUMO 슬러그가 없는 구 이름이면 크롤링을 시도조차 하지 않는다."""
    crawled_path = tmp_path / "crawled_wards.json"

    ensure_ward_crawled("存在しない区", mlit_api_key="x", crawled_wards_path=crawled_path)

    assert not crawled_path.exists()


def test_an_already_crawled_ward_skips_without_touching_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """슬러그가 이미 crawled_wards.json 에 있으면 크롤링 함수를 아예 부르지 않는다."""
    crawled_path = tmp_path / "crawled_wards.json"
    crawled_path.write_text(json.dumps({"nerima": "2026-09-14T00:00:00+00:00"}), encoding="utf-8")

    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("이미 크롤링된 구인데 크롤링 함수가 불렸다")

    monkeypatch.setattr(lazy_new_construction, "_crawl_and_enrich_ward", _fail_if_called)

    ensure_ward_crawled("練馬区", mlit_api_key="x", crawled_wards_path=crawled_path)


def test_a_crawl_failure_is_swallowed_and_not_marked_crawled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """크롤링/보강 중 예외가 나면 조용히 실패하고, 크롤링 완료로 기록하지 않는다
    (다음 질문 때 재시도되어야 하므로)."""
    crawled_path = tmp_path / "crawled_wards.json"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("네트워크 실패")

    monkeypatch.setattr(lazy_new_construction, "_crawl_and_enrich_ward", _boom)

    ensure_ward_crawled("練馬区", mlit_api_key="x", crawled_wards_path=crawled_path)

    assert not crawled_path.exists()


def test_a_successful_crawl_marks_the_ward_crawled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """크롤링이 성공하면 슬러그가 crawled_wards.json 에 기록돼 다음부터 스킵된다."""
    crawled_path = tmp_path / "crawled_wards.json"
    calls: list[tuple[str, str, str]] = []

    def _record_call(ward_ja: str, slug: str, mlit_api_key: str) -> None:
        calls.append((ward_ja, slug, mlit_api_key))

    monkeypatch.setattr(lazy_new_construction, "_crawl_and_enrich_ward", _record_call)

    ensure_ward_crawled("練馬区", mlit_api_key="secret", crawled_wards_path=crawled_path)

    assert calls == [("練馬区", "nerima", "secret")]
    recorded = json.loads(crawled_path.read_text(encoding="utf-8"))
    assert "nerima" in recorded


def test_merge_by_suumo_id_dedupes_and_prefers_the_new_value() -> None:
    existing = [{"suumo_id": "1", "name": "구값"}, {"suumo_id": "2", "name": "그대로"}]
    new = [{"suumo_id": "1", "name": "새값"}]

    merged = _merge_by_suumo_id(existing, new)

    by_id = {row["suumo_id"]: row["name"] for row in merged}
    assert by_id == {"1": "새값", "2": "그대로"}
