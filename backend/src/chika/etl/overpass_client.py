"""Overpass API(OpenStreetMap) HTTP 클라이언트.

공개 API 라 SUUMO 같은 이용약관 문제는 없다(OSM 데이터는 ODbL — 출처
표기 조건으로 자유 이용). 다만 공개 인스턴스(overpass-api.de)는 실측
결과(2026-09-14) 3연속 호출만으로 429(rate limit)를 맞았다 — SuumoClient
와 같은 호출 간격 강제·재시도 백오프를 그대로 적용한다.

mlit_client.py/suumo_client.py 와 같은 transport 주입 패턴이라 테스트가
실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_MIN_INTERVAL_SECONDS = 2.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume)"

Transport = Callable[[str, bytes], bytes]


class OverpassFetchError(RuntimeError):
    """Overpass 쿼리를 받아오지 못했다."""


def _urllib_transport(url: str, body: bytes) -> bytes:
    request = urllib.request.Request(
        url, data=body, headers={"User-Agent": _USER_AGENT}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw: bytes = response.read()
        return raw


class OverpassClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def query(self, overpass_ql: str) -> str:
        """Overpass QL 쿼리 문자열을 실행하고 원본 JSON 텍스트를 돌려준다."""
        self._throttle()
        body = urllib.parse.urlencode({"data": overpass_ql}).encode("utf-8")
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(_OVERPASS_URL, body)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise OverpassFetchError(f"HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise OverpassFetchError(f"연결 실패: {exc.reason}") from exc
            self.calls_made += 1
            return raw.decode("utf-8", errors="replace")
        raise OverpassFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
