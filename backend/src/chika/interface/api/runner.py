"""Agents SDK 스트림을 SSE 이벤트로 옮기는 어댑터.

여기가 이 프로젝트에서 실제로 OpenAI를 호출하는 유일한 지점이다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents import Runner

from chika.interface.agent.agents import build_agents
from chika.interface.agent.state import SessionState
from chika.interface.api.events import Event, text_event, tool_event

#: Responses API 의 텍스트 증분 이벤트.
#:
#: `response.function_call_arguments.delta` 도 `.delta` 문자열을 갖는다 —
#: 타입을 보지 않고 delta 만 흘려보내면 툴 인자 JSON이 사용자 화면에 그대로
#: 찍힌다. 실측으로 확인한 버그다.
_TEXT_DELTA = "response.output_text.delta"


async def run_turn(state: SessionState, message: str) -> AsyncIterator[Event]:
    """대화 한 턴. 텍스트 증분과 툴 결과를 다른 채널로 내보낸다 (스펙 §5.4)."""
    # 대화 이력을 함께 넘긴다. 넘기지 않으면 매 턴이 백지에서 시작해
    # "공원은 몇개야?" 같은 이어지는 질문에 답할 수 없다.
    result = Runner.run_streamed(
        build_agents(), message, context=state, session=state.history
    )

    # 툴 이름은 호출 이벤트에만 있고 결과 이벤트에는 call_id 만 있다.
    names_by_call: dict[str, str] = {}

    async for event in result.stream_events():
        if event.type == "raw_response_event":
            if getattr(event.data, "type", "") != _TEXT_DELTA:
                continue
            delta = getattr(event.data, "delta", None)
            if isinstance(delta, str) and delta:
                yield text_event(delta)
            continue

        if event.type != "run_item_stream_event":
            continue

        item = event.item
        if item.type == "tool_call_item":
            call_id, name = _call_id(item.raw_item), _tool_name(item.raw_item)
            if call_id and name:
                names_by_call[call_id] = name
            continue

        if item.type == "tool_call_output_item":
            call_id = _call_id(item.raw_item)
            yield tool_event(names_by_call.get(call_id or "", "tool"), item.output)


def _attr(raw: Any, key: str) -> str | None:
    """raw_item 은 SDK 버전에 따라 dict 이거나 pydantic 모델이다."""
    value = raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)
    return str(value) if value else None


def _call_id(raw: Any) -> str | None:
    return _attr(raw, "call_id") or _attr(raw, "id")


def _tool_name(raw: Any) -> str | None:
    return _attr(raw, "name")
