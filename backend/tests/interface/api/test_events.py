"""SSE 이벤트 — 스펙 §5.4가 요구하는 '텍스트와 툴 결과 분리'.

rank_areas 결과가 오면 프론트가 지도에 핀을 먼저 찍고, 서술은 그 뒤에 타이핑된다.
한 채널로 섞어 보내면 프론트가 그 순서를 만들 수 없다.
"""

import json

from chika.interface.api.events import (
    done_event,
    error_event,
    text_event,
    tool_event,
)


def _parse(raw: dict) -> tuple[str, dict]:
    return raw["event"], json.loads(raw["data"])


def test_text_and_tool_results_travel_on_different_channels() -> None:
    text_name, _ = _parse(text_event("안녕"))
    tool_name, _ = _parse(tool_event("rank_areas", {"areas": []}))
    assert text_name != tool_name


def test_text_event_carries_the_delta() -> None:
    name, data = _parse(text_event("나카노는"))
    assert name == "text"
    assert data == {"delta": "나카노는"}


def test_tool_event_names_the_tool_and_carries_the_result() -> None:
    name, data = _parse(tool_event("rank_areas", {"areas": [{"station_id": "st_a"}]}))
    assert name == "tool"
    assert data["tool"] == "rank_areas"
    assert data["result"]["areas"][0]["station_id"] == "st_a"


def test_korean_text_is_not_escaped() -> None:
    """SSE 본문에 \\uXXXX가 들어가면 프론트 디버깅이 괴로워진다."""
    _, data = _parse(text_event("신오쿠보"))
    assert data["delta"] == "신오쿠보"
    assert "\\u" not in text_event("신오쿠보")["data"]


def test_done_event_reports_remaining_budget() -> None:
    name, data = _parse(done_event(remaining_today=7))
    assert name == "done"
    assert data["remaining_today"] == 7


def test_error_event_carries_a_code_and_message() -> None:
    name, data = _parse(error_event("rate_limited", "너무 잦다"))
    assert name == "error"
    assert data == {"code": "rate_limited", "message": "너무 잦다"}


def test_events_never_contain_raw_newlines_in_data() -> None:
    """SSE는 개행으로 프레임을 나눈다. data에 생 개행이 있으면 스트림이 깨진다."""
    for raw in (
        text_event("첫 줄\n둘째 줄"),
        error_event("boom", "여러\n줄\n메시지"),
        tool_event("t", {"note": "줄\n바꿈"}),
    ):
        assert "\n" not in raw["data"]
