"""OverpassClient — 스로틀, 재시도. suumo_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.overpass_client import OverpassClient, OverpassFetchError


def test_query_returns_decoded_body() -> None:
    def transport(url: str, body: bytes) -> bytes:
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    assert client.query("[out:json];way(1,2,3,4);out geom;") == '{"elements": []}'


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str, body: bytes) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    assert client.query("q") == '{"elements": []}'
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str, body: bytes) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    client = OverpassClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(OverpassFetchError, match="400"):
        client.query("q")
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_two_seconds_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str, body: bytes) -> bytes:
        return b'{"elements": []}'

    client = OverpassClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.query("q")
    assert sleeps and sleeps[0] > 1.9
