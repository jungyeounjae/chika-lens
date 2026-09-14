"""GsiGeocoder — 국토지리원 주소검색 API 클라이언트."""

from __future__ import annotations

import json
import urllib.error

import pytest

from chika.etl.gsi_geocoder import GsiGeocoder


def _body(results: list[dict[str, object]]) -> bytes:
    return json.dumps(results).encode("utf-8")


def test_a_matched_address_returns_lat_lon() -> None:
    """실측(2026-09-14): 東京都新宿区下落合１ -> lon 139.699585, lat 35.71574."""

    def transport(url: str) -> bytes:
        return _body(
            [
                {
                    "geometry": {"coordinates": [139.699585, 35.71574], "type": "Point"},
                    "properties": {"title": "東京都新宿区下落合一丁目"},
                }
            ]
        )

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    lat, lon = geocoder.geocode("東京都新宿区下落合１")
    assert lat == pytest.approx(35.71574)
    assert lon == pytest.approx(139.699585)


def test_an_unmatched_address_is_missing_not_an_error() -> None:
    def transport(url: str) -> bytes:
        return _body([])

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    assert geocoder.geocode("존재하지 않는 주소") is None


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]
        return _body([{"geometry": {"coordinates": [139.7, 35.7]}, "properties": {}}])

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    assert geocoder.geocode("x") == (35.7, 139.7)
    assert len(attempts) == 2
