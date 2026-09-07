"""HTTP 클라이언트 — 네트워크 없이 가짜 transport로 검증한다."""

import json
import urllib.error

import pytest

from chika.etl.aggregate_client import AggregateApiError, AggregateClient
from chika.etl.aggregate_queries import AggregateQuery

_QUERY = AggregateQuery("cafe", ("cafe",), 4.5)
_PLAIN = AggregateQuery("park", ("park",))


class _Recorder:
    def __init__(self, payload: object = None) -> None:
        self.payload = payload if payload is not None else {"count": "42"}
        self.bodies: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, url: str, body: bytes, headers: dict) -> bytes:
        self.bodies.append(json.loads(body.decode("utf-8")))
        self.headers.append(headers)
        return json.dumps(self.payload).encode("utf-8")


def _client(transport: _Recorder) -> AggregateClient:
    return AggregateClient("SECRET_KEY", transport=transport, sleep=lambda _: None)


def test_count_parses_the_string_encoded_integer() -> None:
    """count는 '42' 문자열로 온다. int 변환을 빠뜨리면 정규화가 조용히 망가진다."""
    assert _client(_Recorder({"count": "42"})).count(_PLAIN, 35.7, 139.7) == 42


def test_missing_count_is_zero() -> None:
    assert _client(_Recorder({})).count(_PLAIN, 35.7, 139.7) == 0


def test_request_carries_the_circle_and_types() -> None:
    rec = _Recorder()
    _client(rec).count(_PLAIN, 35.7056, 139.6659)
    body = rec.bodies[0]
    circle = body["filter"]["locationFilter"]["circle"]
    assert circle["latLng"] == {"latitude": 35.7056, "longitude": 139.6659}
    assert circle["radius"] == 800
    assert body["filter"]["typeFilter"]["includedTypes"] == ["park"]
    assert body["insights"] == ["INSIGHT_COUNT"]


def test_only_operational_places_are_counted() -> None:
    rec = _Recorder()
    _client(rec).count(_PLAIN, 35.7, 139.7)
    assert rec.bodies[0]["filter"]["operatingStatus"] == ["OPERATING_STATUS_OPERATIONAL"]


def test_rating_filter_is_sent_only_when_the_query_has_one() -> None:
    rec = _Recorder()
    client = _client(rec)
    client.count(_QUERY, 35.7, 139.7)
    client.count(_PLAIN, 35.7, 139.7)
    assert rec.bodies[0]["filter"]["ratingFilter"] == {"minRating": 4.5}
    assert "ratingFilter" not in rec.bodies[1]["filter"]


def test_api_key_travels_in_the_header_not_the_url() -> None:
    rec = _Recorder()
    _client(rec).count(_PLAIN, 35.7, 139.7)
    assert rec.headers[0]["X-Goog-Api-Key"] == "SECRET_KEY"


def test_calls_are_counted_for_budget_tracking() -> None:
    rec = _Recorder()
    client = _client(rec)
    for _ in range(3):
        client.count(_PLAIN, 35.7, 139.7)
    assert client.calls_made == 3


def test_a_failed_call_is_not_counted() -> None:
    def failing(url: str, body: bytes, headers: dict) -> bytes:
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    client = AggregateClient("SECRET_KEY", transport=failing, sleep=lambda _: None)
    with pytest.raises(AggregateApiError):
        client.count(_PLAIN, 35.7, 139.7)
    assert client.calls_made == 0


def test_the_api_key_is_masked_in_error_messages() -> None:
    """오류 본문이 키를 에코해도 로그·스택트레이스로 새면 안 된다."""

    def echoing(url: str, body: bytes, headers: dict) -> bytes:
        raise urllib.error.HTTPError(
            url, 400, "Bad Request", {},  # type: ignore[arg-type]
            __import__("io").BytesIO(b'{"error":"bad key SECRET_KEY"}'),
        )

    client = AggregateClient("SECRET_KEY", transport=echoing, sleep=lambda _: None)
    with pytest.raises(AggregateApiError) as exc:
        client.count(_PLAIN, 35.7, 139.7)
    assert "SECRET_KEY" not in str(exc.value)
    assert "<REDACTED>" in str(exc.value)


def test_calls_are_throttled_after_the_first() -> None:
    slept: list[float] = []
    client = AggregateClient("K", transport=_Recorder(), sleep=slept.append)
    client.count(_PLAIN, 35.7, 139.7)
    client.count(_PLAIN, 35.7, 139.7)
    assert slept and all(0 < s <= 1.0 / 15 for s in slept)
