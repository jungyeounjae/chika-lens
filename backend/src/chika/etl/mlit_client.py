"""不動産情報ライブラリ API HTTP 클라이언트.

Aggregate 와 달리 호출당 과금이 없다. 대신 레이트 리밋이 공개돼 있지 않으므로
보수적으로 던지고, 429/5xx 는 지수 백오프로 물러선다.

빈 응답을 성공으로 접지 않는다. 타일에 시설이 없어서 0건인 것과 요청이 잘못돼
0건인 것은 구분되지 않는데, 후자를 조용히 넘기면 지표가 통째로 결측이 되고도
로그에는 아무 흔적이 남지 않는다. 그래서 데이터셋 정체를 `_index` 로 대조한다.
"""

from __future__ import annotations

import gzip
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence

from chika.etl.mlit_datasets import TILE_ZOOM, MlitDataset

BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/"

#: 공개된 상한이 없다. 초당 5건이면 59타일 × 2데이터셋이 25초쯤 걸린다 —
#: 월 1회 배치에 그 정도는 서두를 이유가 없다.
_MIN_INTERVAL_SECONDS = 1.0 / 5

_MAX_ATTEMPTS = 5
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

Transport = Callable[[str, dict[str, str]], tuple[bytes, str]]


class MlitApiError(RuntimeError):
    """API 오류. 메시지에서 키는 마스킹된다."""


def tile_xy(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """WGS84 좌표를 Web Mercator 타일 번호로. API 가 z/x/y 로만 받는다."""
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def tiles_covering(
    points: Iterable[tuple[float, float]],
    zoom: int = TILE_ZOOM,
    margin_m: float = 1000.0,
) -> list[tuple[int, int]]:
    """점들을 여유 반경까지 덮는 타일 집합. 정렬해서 돌려준다 — 실행마다 순서가
    바뀌면 중단 후 재개했을 때 진행률이 무의미해진다.

    역이 타일 경계에 붙어 있으면 반경 800m 안의 시설이 옆 타일에 있다. 여유를
    두지 않으면 그 역만 조용히 과소집계된다.
    """
    tiles: set[tuple[int, int]] = set()
    for lat, lon in points:
        dlat = margin_m / 111_320.0
        dlon = margin_m / (111_320.0 * math.cos(math.radians(lat)))
        # 모서리 넷만 넣으면 여유 반경이 타일보다 클 때 사이 타일이 빈다.
        # 지금 설정(z=13 에서 타일 약 3.9km, 여유 1km)에서는 드러나지 않지만,
        # 줌을 올리거나 여유를 늘리는 순간 조용히 구멍이 생긴다.
        x_min, y_max = tile_xy(lat - dlat, lon - dlon, zoom)
        x_max, y_min = tile_xy(lat + dlat, lon + dlon, zoom)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.add((x, y))
    return sorted(tiles)


def _urllib_transport(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read()
        encoding: str = response.headers.get("Content-Encoding", "")
        return body, encoding


class MlitClient:
    """타일 단위 GeoJSON 조회. 배치가 쓰고 런타임은 쓰지 않는다."""

    def __init__(
        self,
        api_key: str,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def features(
        self, dataset: MlitDataset, x: int, y: int, zoom: int = TILE_ZOOM
    ) -> Sequence[dict[str, object]]:
        """타일 하나의 feature 목록. 호출 1건을 쓴다."""
        query = urllib.parse.urlencode(
            {"response_format": "geojson", "z": zoom, "x": x, "y": y}
        )
        url = f"{BASE_URL}{dataset.endpoint}?{query}"
        payload = self._get_with_retry(url)

        features = payload.get("features") or []
        if not isinstance(features, list):
            raise MlitApiError(f"{dataset.endpoint}: features 가 리스트가 아니다")
        if features:
            self._verify_identity(dataset, features[0])
        return features

    def _verify_identity(self, dataset: MlitDataset, feature: object) -> None:
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        index = str(properties.get("_index", "")) if isinstance(properties, dict) else ""
        if not index.startswith(dataset.index_prefix):
            raise MlitApiError(
                f"{dataset.endpoint} 가 {dataset.index_prefix!r} 가 아니라 "
                f"{index!r} 를 돌려줬다. 엔드포인트 번호가 바뀌었을 수 있다."
            )

    def _get_with_retry(self, url: str) -> dict[str, object]:
        headers = {
            "Ocp-Apim-Subscription-Key": self._api_key,
            "Accept-Encoding": "gzip",
        }
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                raw, encoding = self._transport(url, headers)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")
                raise MlitApiError(
                    f"HTTP {exc.code}: {detail.replace(self._api_key, '<REDACTED>')}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise MlitApiError(f"연결 실패: {exc.reason}") from exc

            self.calls_made += 1
            if encoding == "gzip":
                raw = gzip.decompress(raw)
            decoded: dict[str, object] = json.loads(raw.decode("utf-8"))
            return decoded
        raise MlitApiError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
