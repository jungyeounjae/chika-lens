"""세션 저장.

스펙 §5.5: "예산 12만엔으로 낮추면?"이 오면 이전 `SearchCriteria`를 유지한 채
해당 필드만 교체한다. 세션이 매 요청마다 초기화되면 그 유스케이스가 성립하지 않는다.

프로세스 메모리 기반이라 재시작하면 사라진다. 프로토타입 단계에서는 그것으로
충분하다 — 대화 이력을 영속화하려면 별도 저장소가 필요하고, 그건 개인정보를
보관하기 시작하는 일이라 결정이 따로 필요하다.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable


class SessionStore[T]:
    """LRU + TTL. 세션이 무한히 쌓이면 메모리가 샌다."""

    def __init__(
        self,
        factory: Callable[[], T],
        max_sessions: int = 500,
        ttl_seconds: float = 3600.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._max = max_sessions
        self._ttl = ttl_seconds
        self._now = now
        self._entries: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, session_id: str) -> T:
        """세션을 돌려주고, 없거나 만료됐으면 새로 만든다."""
        if not session_id:
            raise ValueError("session id must not be empty")

        now = self._now()
        entry = self._entries.get(session_id)
        if entry is not None:
            touched_at, session = entry
            if now - touched_at < self._ttl:
                # 활동이 TTL을 갱신한다. 대화 중인 세션이 사라지면 조건이 초기화된다.
                self._entries[session_id] = (now, session)
                self._entries.move_to_end(session_id)
                return session
            del self._entries[session_id]

        session = self._factory()
        self._entries[session_id] = (now, session)
        self._entries.move_to_end(session_id)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
        return session

    def size(self) -> int:
        return len(self._entries)
