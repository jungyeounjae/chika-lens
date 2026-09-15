"""Agents SDK 스트림을 SSE 이벤트로 옮기는 어댑터.

여기가 이 프로젝트에서 실제로 OpenAI를 호출하는 유일한 지점이다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents import Runner

from chika.interface.agent.agents import build_agents
from chika.interface.agent.state import SessionState
from chika.interface.api.events import Event, status_event, text_event, tool_event

#: Responses API 의 텍스트 증분 이벤트.
#:
#: `response.function_call_arguments.delta` 도 `.delta` 문자열을 갖는다 —
#: 타입을 보지 않고 delta 만 흘려보내면 툴 인자 JSON이 사용자 화면에 그대로
#: 찍힌다. 실측으로 확인한 버그다.
_TEXT_DELTA = "response.output_text.delta"

#: 툴 이름 -> 실행 중 상태 문구. ChatGPT·제미나이의 "웹 검색 중..." 같은
#: 실시간 표시를 흉내낸다. 여기 없는 툴은 이름을 그대로 보여준다 —
#: 새 툴을 추가하고 이 표를 잊어도 화면이 비지는 않는다.
_TOOL_STATUS_KO: dict[str, str] = {
    "set_criteria": "조건 확인하는 중...",
    "lookup_station": "역 찾는 중...",
    "rank_areas": "역세권 순위 계산하는 중...",
    "explain_area": "역 정보 분석하는 중...",
    "compare_areas": "비교하는 중...",
    "metric_distribution": "주변 지표 조회하는 중...",
    "ward_price_ranking": "구 단위 시세 조회하는 중...",
    "metric_extremes": "전체 역 정렬하는 중...",
    "hazard_polygons": "재해 구역 3D 데이터 가져오는 중...",
    "zoning_massing": "용도지역 3D 데이터 가져오는 중...",
}


#: 이 툴들은 모델에게는 좌표 없는 압축본만 주고, SSE로는 원본 좌표가 든
#: 전체본을 낸다 — actions.py의 `_stash_full_and_strip_geometry`가 쌓아 둔
#: `state.pending_overlay_payloads`에서 꺼낸다.
_OVERLAY_TOOLS_WITH_STASHED_PAYLOAD = frozenset({"hazard_polygons", "zoning_massing", "park_polygons"})


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
            if name:
                # 결과를 기다리지 않고 바로 내보낸다 — 그래야 "…" 대신
                # 실시간 상태가 뜬다. 결과는 tool_call_output_item 에서
                # 별도로 나간다(아래).
                yield status_event(_TOOL_STATUS_KO.get(name, f"{name} 처리하는 중..."))
            continue

        if item.type == "tool_call_output_item":
            call_id = _call_id(item.raw_item)
            name = names_by_call.get(call_id or "", "tool")
            payload = item.output
            if name in _OVERLAY_TOOLS_WITH_STASHED_PAYLOAD:
                queue = state.pending_overlay_payloads.get(name)
                if queue:
                    payload = queue.pop(0)
            yield tool_event(name, payload)


def _attr(raw: Any, key: str) -> str | None:
    """raw_item 은 SDK 버전에 따라 dict 이거나 pydantic 모델이다."""
    value = raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)
    return str(value) if value else None


def _call_id(raw: Any) -> str | None:
    return _attr(raw, "call_id") or _attr(raw, "id")


def _tool_name(raw: Any) -> str | None:
    return _attr(raw, "name")
