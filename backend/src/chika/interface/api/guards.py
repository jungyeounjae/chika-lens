"""비용 보호 — IP당 속도 제한과 전체 일일 상한.

스펙 §9: "공개 시 비용이 급증할 수 있으므로 IP당 rate limit과 일일 상한을
처음부터 넣는다." 대화 한 번에 OpenAI 비용이 나가므로 나중에 붙일 일이 아니다.

둘을 함께 두는 이유: IP 제한만 있으면 분산 요청에 뚫리고, 일일 상한만 있으면
한 사람이 하루치를 다 쓸 수 있다.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0
DAY_SECONDS = 86_400.0


class GuardRefused(RuntimeError):
    """요청을 받지 않았다. 이 예외는 비용을 쓰기 전에 던진다."""


class RateLimited(GuardRefused):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__(f"요청이 너무 잦다. {retry_after_seconds:.0f}초 후 다시 시도한다.")
        self.retry_after_seconds = retry_after_seconds


class DailyCapReached(GuardRefused):
    def __init__(self) -> None:
        super().__init__("오늘의 요청 한도에 도달했다. 내일 다시 시도한다.")


class CostGuard:
    """프로세스 메모리 기반. 인스턴스가 하나일 때만 정확하다.

    여러 인스턴스로 확장하면 공유 저장소(Redis 등)가 필요하다. 프로토타입
    단계에서는 Cloud Run 인스턴스 1개를 전제한다.
    """

    def __init__(
        self,
        per_ip_per_minute: int,
        daily_total: int,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_ip = per_ip_per_minute
        self._daily_total = daily_total
        self._now = now
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day_started_at = now()
        self._day_count = 0

    def check(self, client_ip: str) -> None:
        """통과하면 조용히 돌아오고, 아니면 GuardRefused를 던진다."""
        now = self._now()
        self._roll_day(now)

        # 속도 제한을 먼저 본다. 거절된 요청이 일일 예산을 깎으면
        # 재시도만으로 하루치가 날아간다.
        window = self._hits[client_ip]
        while window and now - window[0] >= WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self._per_ip:
            raise RateLimited(WINDOW_SECONDS - (now - window[0]))

        if self._day_count >= self._daily_total:
            raise DailyCapReached

        window.append(now)
        self._day_count += 1

    def remaining_today(self) -> int:
        self._roll_day(self._now())
        return max(0, self._daily_total - self._day_count)

    def _roll_day(self, now: float) -> None:
        if now - self._day_started_at >= DAY_SECONDS:
            self._day_started_at = now
            self._day_count = 0
