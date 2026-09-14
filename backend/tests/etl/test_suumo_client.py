"""SuumoClient — 스로틀, 재시도. mlit_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.suumo_client import SuumoClient, SuumoFetchError


def test_fetch_html_returns_decoded_body() -> None:
    def transport(url: str) -> bytes:
        return "<html>ok</html>".encode("utf-8")

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    assert client.fetch_html("https://suumo.jp/x") == "<html>ok</html>"


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b"<html>ok</html>"

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    assert client.fetch_html("https://suumo.jp/x") == "<html>ok</html>"
    assert len(attempts) == 3


def test_a_not_found_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(SuumoFetchError, match="404"):
        client.fetch_html("https://suumo.jp/x")
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_two_seconds_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str) -> bytes:
        return b"<html>ok</html>"

    client = SuumoClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.fetch_html("https://suumo.jp/x")
    assert sleeps and sleeps[0] > 1.9
