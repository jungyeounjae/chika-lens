"""대화 이력 — 실사용에서 드러난 결함.

"히카리가오카는 살기 좋아?" 다음에 "공원은 몇개야?" 라고 물으면 에이전트가
"어느 역을 말씀하시나요?" 라고 되물었다. 매 턴이 백지에서 시작했기 때문이다.

스펙 §5.5는 "Agents SDK 세션 메모리로 유지한다"고 적어놓고 실제로는
Runner 에 새 메시지 한 줄만 넘기고 있었다.
"""

import pytest

from chika.interface.api.memory import InMemorySession


@pytest.fixture
def session() -> InMemorySession:
    return InMemorySession(max_items=6)


async def test_a_fresh_session_is_empty(session: InMemorySession) -> None:
    assert await session.get_items() == []


async def test_items_come_back_in_order(session: InMemorySession) -> None:
    await session.add_items([{"role": "user", "content": "a"}])
    await session.add_items([{"role": "assistant", "content": "b"}])
    items = await session.get_items()
    assert [i["content"] for i in items] == ["a", "b"]  # type: ignore[index]


async def test_the_oldest_turns_are_dropped_when_full(session: InMemorySession) -> None:
    """이력이 무한히 쌓이면 토큰 비용이 매 턴 늘어난다."""
    for i in range(10):
        await session.add_items([{"role": "user", "content": str(i)}])
    items = await session.get_items()
    assert len(items) == 6
    assert [i["content"] for i in items] == ["4", "5", "6", "7", "8", "9"]  # type: ignore[index]


async def test_trim_never_splits_a_function_call_from_its_output() -> None:
    """실사용 오류: "No tool call found for function call output with
    call_id ...". 개수로만 자르면 오래된 턴의 function_call 은 밀려나고
    바로 다음 function_call_output 은 살아남아 응답 API 가 거부한다."""
    session = InMemorySession(max_items=5)
    # 첫 턴: 유저 메시지 + function_call + function_call_output 3개짜리 턴.
    await session.add_items(
        [
            {"role": "user", "content": "first"},
            {"type": "function_call", "call_id": "c1", "name": "lookup_station"},
            {"type": "function_call_output", "call_id": "c1", "output": "..."},
        ]
    )
    # 둘째 턴도 3개 — 합쳐서 6개가 되어 상한(5)을 넘는다.
    await session.add_items(
        [
            {"role": "user", "content": "second"},
            {"type": "function_call", "call_id": "c2", "name": "explain_area"},
            {"type": "function_call_output", "call_id": "c2", "output": "..."},
        ]
    )
    items = await session.get_items()
    # 첫 턴이 통째로 잘려 나가고 둘째 턴만 온전히 남아야 한다 — 개수 상한(5)보다
    # 짝을 지키는 게 우선이라 3개(<=5)로 줄어든다.
    assert [i.get("content") or i.get("call_id") for i in items] == ["second", "c2", "c2"]
    call_ids_with_output = {i["call_id"] for i in items if i.get("type") == "function_call_output"}
    call_ids_with_call = {i["call_id"] for i in items if i.get("type") == "function_call"}
    assert call_ids_with_output == call_ids_with_call


async def test_a_turn_larger_than_the_cap_is_kept_whole() -> None:
    """상한(3)보다 큰 턴(5개) 하나만 있으면 자를 턴 경계가 없다 — 상한을
    넘기더라도 그 턴을 통째로 유지한다."""
    session = InMemorySession(max_items=3)
    await session.add_items(
        [
            {"role": "user", "content": "only"},
            {"type": "function_call", "call_id": "c1"},
            {"type": "function_call_output", "call_id": "c1"},
            {"type": "function_call", "call_id": "c2"},
            {"type": "function_call_output", "call_id": "c2"},
        ]
    )
    assert len(await session.get_items()) == 5


async def test_limit_returns_the_most_recent(session: InMemorySession) -> None:
    for i in range(4):
        await session.add_items([{"role": "user", "content": str(i)}])
    assert [i["content"] for i in await session.get_items(limit=2)] == ["2", "3"]  # type: ignore[index]


async def test_pop_removes_the_last_item(session: InMemorySession) -> None:
    await session.add_items([{"role": "user", "content": "a"}])
    await session.add_items([{"role": "user", "content": "b"}])
    popped = await session.pop_item()
    assert popped["content"] == "b"  # type: ignore[index]
    assert len(await session.get_items()) == 1


async def test_pop_on_an_empty_session_returns_none(session: InMemorySession) -> None:
    assert await session.pop_item() is None


async def test_clear_empties_the_session(session: InMemorySession) -> None:
    await session.add_items([{"role": "user", "content": "a"}])
    await session.clear_session()
    assert await session.get_items() == []


async def test_history_stays_in_our_process(session: InMemorySession) -> None:
    """OpenAI 서버에 대화를 보관하면 개인정보 보관 결정이 따로 필요하다.

    프로세스 메모리에 두면 재시작으로 사라지고, 그것이 프로토타입에는 옳다.
    """
    assert not hasattr(session, "conversation_id")
