"""Nominatim(OpenStreetMap) 지오코딩 API HTTP 클라이언트.

Nominatim 공식 사용 정책 — 초당 1회 이하, 식별 가능한 User-Agent 필수
(https://operations.osmfoundation.org/policies/nominatim/). overpass_client.py
와 같은 transport 주입 패턴이라 테스트가 실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

_BASE_URL = "https://nominatim.openstreetmap.org/search"
_MIN_INTERVAL_SECONDS = 1.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume)"

Transport = Callable[[str], bytes]


class NominatimFetchError(RuntimeError):
    """Nominatim 검색 요청이 실패했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw: bytes = response.read()
        return raw


class NominatimClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0

    def search(self, query: str, limit: int) -> str:
        """질의 문자열로 검색하고 원본 JSON 텍스트를 돌려준다."""
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "limit": limit, "countrycodes": "jp"}
        )
        url = f"{_BASE_URL}?{params}"
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise NominatimFetchError(f"HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise NominatimFetchError(f"연결 실패: {exc.reason}") from exc
            return raw.decode("utf-8", errors="replace")
        raise NominatimFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
