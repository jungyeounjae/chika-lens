"""FastAPI + SSE 엔드포인트.

런너를 주입 가능하게 둔 이유는 테스트다. 실제 LLM 왕복은 키가 필요하고 돈이
드므로, 테스트는 가짜 런너로 스트리밍·가드·세션 경로를 전부 검증한다.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from chika.interface.agent.state import SessionState
from chika.interface.api.events import Event, done_event, error_event
from chika.interface.api.guards import CostGuard, DailyCapReached, GuardRefused, RateLimited
from chika.interface.api.sessions import SessionStore
from chika.interface.cli import build_real_session


class AgentRunner(Protocol):
    """대화 한 턴을 SSE 이벤트 스트림으로 돌려준다."""

    def __call__(self, state: SessionState, message: str) -> AsyncIterator[Event]: ...


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


def create_app(
    runner: AgentRunner,
    session_factory: Callable[[], SessionState] | None = None,
    guard: CostGuard | None = None,
) -> FastAPI:
    app = FastAPI(title="Chika Lens", docs_url="/docs")

    # 프론트가 다른 포트에서 뜨므로 CORS 가 필요하다.
    # 와일드카드를 쓰지 않는다 — 공개되면 누구나 이 API 를 자기 사이트에서
    # 호출할 수 있고, 그 비용은 우리 OpenAI 청구서로 온다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.environ.get(
                "CHIKA_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
            ).split(",")
            if origin.strip()
        ],
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
    )

    factory = session_factory or _default_session_factory
    sessions: SessionStore[SessionState] = SessionStore(factory)
    cost_guard = guard or CostGuard(
        per_ip_per_minute=int(os.environ.get("CHIKA_RATE_PER_MIN", "6")),
        daily_total=int(os.environ.get("CHIKA_DAILY_CAP", "200")),
    )

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {
            "ok": True,
            "sessions": sessions.size(),
            "remaining_today": cost_guard.remaining_today(),
        }

    @app.post("/chat")
    async def chat(body: ChatRequest, request: Request) -> EventSourceResponse:
        """SSE 스트림. 가드는 스트림을 열기 전에 본다 — 비용을 쓰기 전에 거절한다."""
        client_ip = _client_ip(request)
        try:
            cost_guard.check(client_ip)
        except GuardRefused as refused:
            code = "rate_limited" if isinstance(refused, RateLimited) else "daily_cap"
            return EventSourceResponse(
                _single(error_event(code, str(refused))), status_code=429
            )

        state = sessions.get(body.session_id)

        async def stream() -> AsyncIterator[Event]:
            try:
                async for event in runner(state, body.message):
                    yield event
            except Exception as exc:  # noqa: BLE001 - 스트림 중 오류를 이벤트로 전달
                yield error_event("agent_error", str(exc))
            yield done_event(cost_guard.remaining_today())

        return EventSourceResponse(stream())

    return app


async def _single(event: Event) -> AsyncIterator[Event]:
    yield event


def _client_ip(request: Request) -> str:
    """프록시 뒤에서는 X-Forwarded-For 의 첫 항목이 실제 클라이언트다.

    Cloud Run 은 이 헤더를 붙인다. 헤더는 위조 가능하므로 이것만으로 인증하지
    않고, 비용 제한 용도로만 쓴다.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _default_session_factory() -> SessionState:
    return build_real_session()


__all__ = ["AgentRunner", "ChatRequest", "CostGuard", "DailyCapReached", "create_app"]
