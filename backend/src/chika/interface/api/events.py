"""SSE 이벤트 구성.

스펙 §5.4: 텍스트와 툴 결과를 **다른 채널로** 보낸다. `rank_areas` 결과가 오면
프론트가 지도에 핀을 먼저 찍고 서술은 그 뒤에 타이핑된다 — 한 채널로 섞으면
프론트가 그 순서를 만들 수 없다.
"""

from __future__ import annotations

import json
from typing import Any

#: sse-starlette 의 EventSourceResponse 가 받는 dict 형태.
Event = dict[str, str]


def _encode(payload: object) -> str:
    # ensure_ascii=False: 한국어가 \uXXXX 로 나가면 프론트 디버깅이 괴로워진다.
    # SSE는 개행으로 프레임을 나누므로 data에 생 개행이 있으면 스트림이 깨진다.
    return json.dumps(payload, ensure_ascii=False).replace("\n", "\\n")


def text_event(delta: str) -> Event:
    """LLM 서술의 증분."""
    return {"event": "text", "data": _encode({"delta": delta})}


def tool_event(tool: str, result: Any) -> Event:
    """툴 반환값. 프론트가 지도·표를 그리는 재료다."""
    return {"event": "tool", "data": _encode({"tool": tool, "result": result})}


def status_event(text: str) -> Event:
    """툴이 실행되는 동안의 중간 상태 — "역세권 순위 계산 중..." 같은 것.

    `tool_event` 는 툴이 끝난 뒤에만 나가서, 그 사이 프론트가 아무 신호도
    못 받고 정적 "…" 만 보여주고 있었다. 이건 그 공백을 메운다.
    """
    return {"event": "status", "data": _encode({"text": text})}


def done_event(remaining_today: int) -> Event:
    """스트림 종료. 남은 일일 예산을 함께 알려 프론트가 표시할 수 있게 한다."""
    return {"event": "done", "data": _encode({"remaining_today": remaining_today})}


def error_event(code: str, message: str) -> Event:
    return {"event": "error", "data": _encode({"code": code, "message": message})}
