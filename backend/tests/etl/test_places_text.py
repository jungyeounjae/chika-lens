"""지표 2 — 한국 식자재·미용 시설.

Places API (New) Text Search. Aggregate API에 '한국 식자재점' 타입이 없어
텍스트 검색으로 보완한다 (스펙 §3.1).
"""

import json

import pytest

from chika.etl.places_text import (
    COUNTED_TYPE,
    KOREAN_QUERIES,
    TextSearchClient,
    bounding_rectangle,
    count_korean_shops,
)


class _Recorder:
    def __init__(self, *responses: list[dict]) -> None:
        self.responses = list(responses)
        self.bodies: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, url: str, body: bytes, headers: dict) -> bytes:
        self.bodies.append(json.loads(body.decode()))
        self.headers.append(headers)
        payload = self.responses.pop(0) if self.responses else []
        return json.dumps({"places": payload}).encode()


def _client(rec: _Recorder) -> TextSearchClient:
    return TextSearchClient("SECRET", transport=rec, sleep=lambda _: None)


# --- 경계 사각형 ---


def test_rectangle_encloses_the_radius() -> None:
    """Text Search 의 locationRestriction 은 원이 아니라 사각형만 받는다."""
    rect = bounding_rectangle(35.7, 139.7, 800.0)["rectangle"]
    assert rect["low"]["latitude"] < 35.7 < rect["high"]["latitude"]
    assert rect["low"]["longitude"] < 139.7 < rect["high"]["longitude"]


def test_longitude_span_accounts_for_latitude() -> None:
    """도쿄 위도에서 경도 1도는 위도 1도보다 짧다. 보정하지 않으면 동서로 좁아진다."""
    rect = bounding_rectangle(35.7, 139.7, 800.0)["rectangle"]
    lat_span = rect["high"]["latitude"] - rect["low"]["latitude"]
    lon_span = rect["high"]["longitude"] - rect["low"]["longitude"]
    assert lon_span > lat_span


# --- 검색 ---


def test_search_sends_the_query_and_rectangle() -> None:
    rec = _Recorder([])
    _client(rec).search("韓国食品", 35.7, 139.7)
    body = rec.bodies[0]
    assert body["textQuery"] == "韓国食品"
    assert "rectangle" in body["locationRestriction"]
    assert body["languageCode"] == "ja"


def test_search_requests_only_the_place_id() -> None:
    """필드 마스크가 과금 티어를 정한다.

    places.id 만 요청하면 Text Search Essentials (IDs Only) — 무료 무제한이다.
    이름·좌표·타입을 하나라도 받으면 Pro(월 5,000)로 올라간다.
    """
    rec = _Recorder([])
    _client(rec).search("韓国食品", 35.7, 139.7)
    assert rec.headers[0]["X-Goog-FieldMask"] == "places.id"


def test_search_returns_place_ids() -> None:
    rec = _Recorder([{"id": "p1"}, {"id": "p2"}])
    assert _client(rec).search("韓国食品", 35.7, 139.7) == ["p1", "p2"]


def test_the_api_key_is_masked_in_errors() -> None:
    import urllib.error
    from io import BytesIO

    def echoing(url: str, body: bytes, headers: dict) -> bytes:
        raise urllib.error.HTTPError(
            url, 400, "Bad", {},  # type: ignore[arg-type]
            BytesIO(b'{"error":"bad key SECRET"}'),
        )

    client = TextSearchClient("SECRET", transport=echoing, sleep=lambda _: None)
    with pytest.raises(RuntimeError) as exc:
        client.search("q", 35.7, 139.7)
    assert "SECRET" not in str(exc.value)


# --- 집계 ---


def test_duplicate_place_ids_are_counted_once() -> None:
    rec = _Recorder([{"id": "p1"}, {"id": "p1"}, {"id": "p2"}])
    assert count_korean_shops(_client(rec), 35.7, 139.7) == 2


def test_the_type_filter_travels_in_the_request_not_the_response() -> None:
    """응답에서 primaryType 을 보고 거르면 두 가지 손해가 있다:
    필드 마스크가 Pro 티어로 올라가고, 서버가 20건으로 자른 뒤에 걸러
    매칭을 잃는다 (실측 신오쿠보 10 -> 16).
    """
    rec = _Recorder([{"id": "p1"}])
    count_korean_shops(_client(rec), 35.7, 139.7)
    assert rec.bodies[0]["includedType"] == COUNTED_TYPE


def test_the_field_mask_stays_on_the_free_tier() -> None:
    """places.id 만 요청하면 Text Search Essentials (IDs Only) — 무료 무제한.
    필드를 하나라도 더 넣으면 Pro(월 5,000)로 올라간다.
    """
    rec = _Recorder([{"id": "p1"}])
    count_korean_shops(_client(rec), 35.7, 139.7)
    assert rec.headers[0]["X-Goog-FieldMask"] == "places.id"


def test_an_area_with_nothing_counts_zero() -> None:
    assert count_korean_shops(_client(_Recorder([])), 35.7, 139.7) == 0


def test_one_call_per_query_term() -> None:
    rec = _Recorder([], [])
    count_korean_shops(_client(rec), 35.7, 139.7)
    assert len(rec.bodies) == len(KOREAN_QUERIES)


def test_query_terms_are_not_redundant() -> None:
    """韓国食材는 韓国食品의 중복이고, 韓国コスメ는 일반 소매점을 잡아온다."""
    assert "韓国食材" not in KOREAN_QUERIES
    assert "韓国コスメ" not in KOREAN_QUERIES
    assert len(KOREAN_QUERIES) == len(set(KOREAN_QUERIES))
