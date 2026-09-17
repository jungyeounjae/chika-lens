"""NominatimGeocoder — Nominatim 응답 파싱 + LandmarkMatch 변환."""

from __future__ import annotations

import json

import pytest

from chika.etl.nominatim_client import NominatimClient, NominatimFetchError
from chika.infrastructure.nominatim_geocoder import NominatimGeocoder


def _client_returning(elements: list[dict[str, object]]) -> NominatimClient:
    def transport(url: str) -> bytes:
        return json.dumps(elements).encode()

    return NominatimClient(transport=transport, sleep=lambda _: None)


def test_a_named_result_is_parsed_into_a_landmark_match() -> None:
    client = _client_returning(
        [
            {
                "name": "新宿御苑",
                "lat": "35.6851",
                "lon": "139.7095",
                "display_name": "新宿御苑, 東京都",
            }
        ]
    )
    geocoder = NominatimGeocoder(client)

    matches = geocoder.search("신주쿠교엔", limit=3)

    assert len(matches) == 1
    assert matches[0].name == "新宿御苑"
    assert matches[0].lat == 35.6851
    assert matches[0].lon == 139.7095


def test_a_result_without_a_name_falls_back_to_display_name() -> None:
    client = _client_returning(
        [{"lat": "35.68", "lon": "139.70", "display_name": "内藤町, 新宿区, 東京都"}]
    )
    geocoder = NominatimGeocoder(client)

    matches = geocoder.search("q", limit=3)

    assert matches[0].name == "内藤町"


def test_an_empty_array_returns_no_matches() -> None:
    client = _client_returning([])
    geocoder = NominatimGeocoder(client)
    assert geocoder.search("존재하지 않는 곳", limit=3) == []


def test_a_non_json_response_raises_a_fetch_error() -> None:
    def transport(url: str) -> bytes:
        return b"not json"

    client = NominatimClient(transport=transport, sleep=lambda _: None)
    geocoder = NominatimGeocoder(client)

    with pytest.raises(NominatimFetchError):
        geocoder.search("q", limit=3)
