"""MLIT HTTP 클라이언트 — 타일 계산, 정체 검증, 재시도."""

from __future__ import annotations

import gzip
import json
import urllib.error

import pytest

from chika.etl.mlit_client import MlitApiError, MlitClient, tile_xy, tiles_covering
from chika.etl.mlit_datasets import PRESCHOOL, SCHOOL


def _body(features: list[dict[str, object]]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def _feature(index: str) -> dict[str, object]:
    return {
        "geometry": {"type": "Point", "coordinates": [139.7, 35.7]},
        "properties": {"_id": "a", "_index": index},
    }


# --- 타일 ---


def test_tile_numbers_match_the_web_mercator_scheme() -> None:
    """신주쿠역 z=13 은 (7275, 3225). API 가 z/x/y 로만 받는다."""
    assert tile_xy(35.6938, 139.7036, 13) == (7275, 3225)


def test_a_station_on_a_tile_edge_pulls_in_the_neighbouring_tile() -> None:
    """여유를 두지 않으면 반경 안의 시설이 옆 타일에 있어 그 역만 과소집계된다."""
    edge_lat, edge_lon = 35.6938, 139.7036
    x, y = tile_xy(edge_lat, edge_lon, 13)
    covering = tiles_covering([(edge_lat, edge_lon)], zoom=13, margin_m=5000.0)
    assert (x, y) in covering
    assert len(covering) > 1


def test_tile_order_is_deterministic() -> None:
    """순서가 실행마다 바뀌면 중단 후 재개했을 때 진행률이 무의미해진다."""
    points = [(35.70, 139.70), (35.75, 139.80), (35.65, 139.65)]
    assert tiles_covering(points) == tiles_covering(list(reversed(points)))


# --- 응답 처리 ---


def test_gzip_responses_are_decompressed() -> None:
    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        return gzip.compress(_body([_feature("bs006_preschool_2024")])), "gzip"

    client = MlitClient("k", transport=transport, sleep=lambda _: None)
    assert len(client.features(PRESCHOOL, 1, 1)) == 1


def test_a_wrong_dataset_is_rejected_rather_than_counted() -> None:
    """엔드포인트 번호를 잘못 적으면 다른 데이터셋이 200으로 조용히 온다.

    값이 아니라 정체를 대조하지 않으면 지표가 통째로 엉뚱한 것을 세게 된다.
    """
    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        return _body([_feature("bs005_school_2024")]), ""

    client = MlitClient("k", transport=transport, sleep=lambda _: None)
    with pytest.raises(MlitApiError, match="bs006_preschool"):
        client.features(PRESCHOOL, 1, 1)


def test_an_empty_tile_is_a_valid_answer() -> None:
    """시설이 없는 타일이 실제로 있다 (도쿄만 위 등)."""
    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        return _body([]), ""

    client = MlitClient("k", transport=transport, sleep=lambda _: None)
    assert client.features(SCHOOL, 1, 1) == []


# --- 재시도 ---


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return _body([_feature("bs006_preschool_2024")]), ""

    client = MlitClient("k", transport=transport, sleep=lambda _: None)
    assert len(client.features(PRESCHOOL, 1, 1)) == 1
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried() -> None:
    """400 은 다시 보내도 400 이다. 재시도는 시간만 버린다."""
    attempts: list[int] = []

    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    client = MlitClient("k", transport=transport, sleep=lambda _: None)
    with pytest.raises(MlitApiError, match="400"):
        client.features(PRESCHOOL, 1, 1)
    assert len(attempts) == 1


def test_the_api_key_never_appears_in_an_error_message() -> None:
    """오류 메시지는 로그와 이슈로 흘러간다."""
    secret = "super-secret-key"

    class _Err(urllib.error.HTTPError):
        def read(self, *args: object, **kwargs: object) -> bytes:
            return f"denied for {secret}".encode()

    def transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
        raise _Err(url, 403, "Forbidden", {}, None)  # type: ignore[arg-type]

    client = MlitClient(secret, transport=transport, sleep=lambda _: None)
    with pytest.raises(MlitApiError) as caught:
        client.features(PRESCHOOL, 1, 1)
    assert secret not in str(caught.value)
    assert "<REDACTED>" in str(caught.value)
