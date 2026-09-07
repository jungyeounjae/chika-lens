"""지표 2 — 한국 식자재·미용 시설.

Places API (New) Text Search. Aggregate API에 '한국 식자재점' 타입이 없어
텍스트 검색으로 보완한다 (스펙 §3.1).
"""

import json

import pytest

from chika.etl.places_text import (
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


def test_search_requests_only_id_and_type() -> None:
    """필드 마스크가 과금 티어를 정한다. 이름·좌표를 받으면 상위 SKU가 된다."""
    rec = _Recorder([])
    _client(rec).search("韓国食品", 35.7, 139.7)
    mask = rec.headers[0]["X-Goog-FieldMask"]
    assert set(mask.split(",")) == {"places.id", "places.primaryType"}


def test_search_returns_id_and_type_pairs() -> None:
    rec = _Recorder([{"id": "p1", "primaryType": "asian_grocery_store"}])
    assert _client(rec).search("韓国食品", 35.7, 139.7) == [("p1", "asian_grocery_store")]


def test_a_place_without_a_type_is_still_counted() -> None:
    rec = _Recorder([{"id": "p1"}])
    assert _client(rec).search("q", 35.7, 139.7) == [("p1", "")]


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
    rec = _Recorder(
        [{"id": "p1", "primaryType": "asian_grocery_store"},
         {"id": "p1", "primaryType": "asian_grocery_store"},
         {"id": "p2", "primaryType": "asian_grocery_store"}],
    )
    assert count_korean_shops(_client(rec), 35.7, 139.7) == 2


def test_only_asian_grocery_stores_are_counted() -> None:
    """상업지구에서 텍스트 검색이 일반 소매점을 무차별로 잡아온다 (스펙 §6.2.3).

    검색어가 이미 '한국'을 강제하므로, 타입 필터는 식자재점이 아닌 것을 걸러낸다.
    """
    rec = _Recorder([
        {"id": "p1", "primaryType": "asian_grocery_store"},
        {"id": "p2", "primaryType": "korean_restaurant"},
        {"id": "p3", "primaryType": "shopping_mall"},
        {"id": "p4", "primaryType": "drugstore"},
        {"id": "p5", "primaryType": "cosmetics_store"},
    ])
    assert count_korean_shops(_client(rec), 35.7, 139.7) == 1


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
