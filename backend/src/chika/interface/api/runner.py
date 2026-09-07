"""Agents SDK 스트림을 SSE 이벤트로 옮기는 어댑터.

여기가 이 프로젝트에서 실제로 OpenAI를 호출하는 유일한 지점이다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from agents import Runner

from chika.interface.agent.agents import build_agents
from chika.interface.agent.state import SessionState
from chika.interface.api.events import Event, text_event, tool_event


async def run_turn(state: SessionState, message: str) -> AsyncIterator[Event]:
    """대화 한 턴. 텍스트 증분과 툴 결과를 다른 채널로 내보낸다 (스펙 §5.4)."""
    result = Runner.run_streamed(build_agents(), message, context=state)

    async for event in result.stream_events():
        # 텍스트 증분
        if event.type == "raw_response_event":
            delta = getattr(event.data, "delta", None)
            if isinstance(delta, str) and delta:
                yield text_event(delta)
            continue

        # 툴 반환값 — 프론트가 지도를 그리는 재료다
        if event.type == "run_item_stream_event" and event.item.type == "tool_call_output_item":
            raw = getattr(event.item, "raw_item", None)
            name = ""
            if isinstance(raw, dict):
                name = str(raw.get("name", ""))
            yield tool_event(name or "tool", event.item.output)
