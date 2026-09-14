"""SUUMO 신축 분양 페이지 HTTP 클라이언트.

공개 사이트 스크래핑이다 — robots.txt 확인(2026-09-14, `/ms/shinchiku/tokyo/sc_*/`
계열은 불허 목록에 없음) 후 개인용으로 얌전히 돈다: 요청 간격 2초 이상,
User-Agent 로 자기 신원을 밝힌다(개인 이메일 등은 넣지 않는다).

robots.txt 는 크롤러 에티켓 신호일 뿐 법적 허가가 아니다 — 실제 이용약관
(SUUMO ご利用規約 제2조/제3조(7))은 콘텐츠 사용을 개인 사적 이용 범위로
제한하고 상업 목적 이용을 금지한다. 이 크롤러의 산출물은 로컬 전용, 개인
용도로만 쓴다 — 공개 저장소 커밋 금지, 재배포 금지, 다중 사용자 서비스로
노출 금지 (스펙 §2.3.1, `docs/superpowers/specs/2026-09-03-chika-lens-design.md`).

mlit_client.py 와 같은 transport 주입 패턴이라 테스트가 실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable

_MIN_INTERVAL_SECONDS = 2.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume batch)"

Transport = Callable[[str], bytes]


class SuumoFetchError(RuntimeError):
    """페이지를 받아오지 못했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body: bytes = response.read()
        return body


class SuumoClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def fetch_html(self, url: str) -> str:
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise SuumoFetchError(f"HTTP {exc.code}: {url}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise SuumoFetchError(f"연결 실패: {exc.reason}") from exc
            self.calls_made += 1
            return raw.decode("utf-8", errors="replace")
        raise SuumoFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다: {url}")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
