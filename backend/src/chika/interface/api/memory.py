"""대화 이력.

실사용에서 드러난 결함을 메운다. "히카리가오카는 살기 좋아?" 다음에
"공원은 몇개야?" 라고 물으면 에이전트가 "어느 역을 말씀하시나요?" 라고 되물었다 —
매 턴이 백지에서 시작했기 때문이다.

**이력은 우리 프로세스 안에만 둔다.** SDK의 `OpenAIConversationsSession` 을 쓰면
대화가 OpenAI 서버에 보관되는데, 그건 개인정보를 남기기 시작하는 일이라 별도
결정이 필요하다. 프로세스 메모리는 재시작으로 사라지고, 프로토타입에는 그것이 맞다.
"""

from __future__ import annotations

from collections import deque
from typing import Any

#: 한 세션이 들고 가는 최대 아이템 수.
#:
#: 이력이 무한히 쌓이면 토큰 비용이 매 턴 늘어난다. 사용자·어시스턴트·툴 호출이
#: 각각 아이템 하나이므로, 40이면 대화 10턴 남짓이다.
DEFAULT_MAX_ITEMS = 40


class InMemorySession:
    """Agents SDK 의 `Session` 프로토콜 구현. 프로세스 메모리 기반."""

    def __init__(self, session_id: str = "default", max_items: int = DEFAULT_MAX_ITEMS) -> None:
        self.session_id = session_id
        self._items: deque[Any] = deque(maxlen=max_items)

    async def get_items(self, limit: int | None = None) -> list[Any]:
        items = list(self._items)
        return items if limit is None else items[-limit:]

    async def add_items(self, items: list[Any]) -> None:
        self._items.extend(items)

    async def pop_item(self) -> Any | None:
        return self._items.pop() if self._items else None

    async def clear_session(self) -> None:
        self._items.clear()
