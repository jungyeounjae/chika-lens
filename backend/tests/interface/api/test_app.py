"""엔드포인트 — 가짜 러너로 검증한다. 실제 LLM 왕복은 키가 필요하고 돈이 든다."""

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from chika.interface.agent.state import SessionState
from chika.interface.api.app import create_app
from chika.interface.api.events import Event, text_event, tool_event
from chika.interface.api.guards import CostGuard


def _echo_runner(state: SessionState, message: str) -> AsyncIterator[Event]:
    async def gen() -> AsyncIterator[Event]:
        yield tool_event("rank_areas", {"areas": [{"station_id": "st_a"}]})
        yield text_event(f"받았다: {message}")

    return gen()


def _client(runner=_echo_runner, guard: CostGuard | None = None) -> TestClient:
    seen: list[str] = []

    def factory() -> SessionState:
        seen.append("built")
        return SessionState(usecases=None)  # type: ignore[arg-type]

    app = create_app(runner, session_factory=factory, guard=guard)
    client = TestClient(app)
    client.sessions_built = seen  # type: ignore[attr-defined]
    return client


def _events(response) -> list[tuple[str, dict]]:  # type: ignore[no-untyped-def]
    out, name = [], None
    for line in response.text.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and name:
            out.append((name, json.loads(line.split(":", 1)[1].strip())))
    return out


def test_health_reports_budget_and_sessions() -> None:
    body = _client().get("/healthz").json()
    assert body["ok"] is True
    assert "remaining_today" in body


def test_chat_streams_tool_results_before_text() -> None:
    """스펙 §5.4 — 지도가 설명보다 먼저 떠야 한다."""
    response = _client().post("/chat", json={"session_id": "s1", "message": "안녕"})
    names = [name for name, _ in _events(response)]
    assert names.index("tool") < names.index("text")


def test_chat_ends_with_done() -> None:
    response = _client().post("/chat", json={"session_id": "s1", "message": "안녕"})
    assert _events(response)[-1][0] == "done"


def test_the_same_session_id_reuses_state() -> None:
    """스펙 §5.5 — 조건 되돌리기가 성립하려면 세션이 유지돼야 한다."""
    client = _client()
    for _ in range(2):
        client.post("/chat", json={"session_id": "s1", "message": "안녕"})
    assert len(client.sessions_built) == 1  # type: ignore[attr-defined]


def test_a_different_session_id_gets_fresh_state() -> None:
    client = _client()
    client.post("/chat", json={"session_id": "s1", "message": "안녕"})
    client.post("/chat", json={"session_id": "s2", "message": "안녕"})
    assert len(client.sessions_built) == 2  # type: ignore[attr-defined]


def test_rate_limited_requests_get_429_without_running_the_agent() -> None:
    ran: list[str] = []

    def spy(state: SessionState, message: str) -> AsyncIterator[Event]:
        ran.append(message)
        return _echo_runner(state, message)

    guard = CostGuard(per_ip_per_minute=1, daily_total=100, now=lambda: 0.0)
    client = _client(runner=spy, guard=guard)
    client.post("/chat", json={"session_id": "s1", "message": "1"})
    second = client.post("/chat", json={"session_id": "s1", "message": "2"})
    assert second.status_code == 429
    assert ran == ["1"]  # 거절된 요청은 에이전트를 돌리지 않는다 = 비용 0


def test_the_daily_cap_also_returns_429() -> None:
    guard = CostGuard(per_ip_per_minute=100, daily_total=1, now=lambda: 0.0)
    client = _client(guard=guard)
    client.post("/chat", json={"session_id": "s1", "message": "1"})
    second = client.post("/chat", json={"session_id": "s1", "message": "2"})
    assert second.status_code == 429
    assert _events(second)[0][1]["code"] == "daily_cap"


def test_an_agent_failure_becomes_an_error_event_not_a_dropped_stream() -> None:
    def failing(state: SessionState, message: str) -> AsyncIterator[Event]:
        async def gen() -> AsyncIterator[Event]:
            yield text_event("시작")
            raise RuntimeError("모델 오류")

        return gen()

    response = _client(runner=failing).post(
        "/chat", json={"session_id": "s1", "message": "안녕"}
    )
    names = [name for name, _ in _events(response)]
    assert "error" in names
    assert names[-1] == "done"


def test_an_empty_message_is_rejected() -> None:
    assert _client().post("/chat", json={"session_id": "s1", "message": ""}).status_code == 422


def test_an_overlong_message_is_rejected() -> None:
    """길이 제한이 없으면 한 요청으로 토큰 비용을 태울 수 있다."""
    body = {"session_id": "s1", "message": "가" * 3000}
    assert _client().post("/chat", json=body).status_code == 422
