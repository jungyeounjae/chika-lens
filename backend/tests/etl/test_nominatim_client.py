"""NominatimClient — 스로틀, 재시도. overpass_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.nominatim_client import NominatimClient, NominatimFetchError


def test_search_returns_decoded_body() -> None:
    def transport(url: str) -> bytes:
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    assert client.search("新宿御苑", limit=3) == "[]"


def test_search_url_carries_query_limit_and_country_filter() -> None:
    seen_urls: list[str] = []

    def transport(url: str) -> bytes:
        seen_urls.append(url)
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    client.search("新宿御苑", limit=3)

    assert len(seen_urls) == 1
    assert "q=" in seen_urls[0]
    assert "limit=3" in seen_urls[0]
    assert "countrycodes=jp" in seen_urls[0]


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    assert client.search("q", limit=1) == "[]"
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(NominatimFetchError, match="400"):
        client.search("q", limit=1)
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_one_second_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str) -> bytes:
        return b"[]"

    client = NominatimClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.search("q", limit=1)
    assert sleeps and sleeps[0] > 0.9
