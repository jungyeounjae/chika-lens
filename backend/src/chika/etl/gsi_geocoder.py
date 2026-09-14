"""국토지리원(GSI) 주소검색 API — 무료, 키 불필요.

https://msearch.gsi.go.jp/address-search/AddressSearch?q=<주소>
실측(2026-09-14): "東京都新宿区下落合１" -> lon 139.699585, lat 35.71574
(coordinates 는 [lon, lat] 순서로 온다).

SUUMO 물건의 소재지는 도도부현이 빠져 있다("新宿区下落合１") — 호출부가
"東京都" 를 붙여서 넘겨야 한다. 여기서는 붙이지 않는다: 이 모듈은 도쿄
전용이 아니라 순수 지오코딩 어댑터이기 때문이다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

BASE_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

_MIN_INTERVAL_SECONDS = 0.5
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume batch)"

Transport = Callable[[str], bytes]


class GeocodeFetchError(RuntimeError):
    """지오코딩 요청이 실패했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        body: bytes = response.read()
        return body


class GsiGeocoder:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0

    def geocode(self, address: str) -> tuple[float, float] | None:
        """(lat, lon). 매칭 실패 시 None(결측) — 주소 하나가 안 풀린다고 배치
        전체를 세울 이유가 없다(MLIT API 호출과 달리 이건 보조 지오코딩)."""
        query = urllib.parse.urlencode({"q": address})
        url = f"{BASE_URL}?{query}"
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise GeocodeFetchError(f"HTTP {exc.code}: {address!r}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise GeocodeFetchError(f"연결 실패: {exc.reason}") from exc

            results = json.loads(raw.decode("utf-8"))
            if not isinstance(results, list) or not results:
                return None
            geometry = results[0].get("geometry", {})
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                return None
            return float(coordinates[1]), float(coordinates[0])
        raise GeocodeFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다: {address!r}")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
