"""에이전트 배선만 확인한다. LLM 호출은 하지 않는다."""

import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.state import SessionState, UseCases

pytest.importorskip("agents", reason="openai-agents 미설치 환경에서는 건너뛴다")

from chika.interface.agent.agents import build_agents  # noqa: E402


def _state() -> SessionState:
    stations, raws, commute, prices = build_seed(count=10)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
        )
    )


def test_entry_agent_is_intake_and_hands_off_to_analysis() -> None:
    intake = build_agents(_state())
    assert intake.name == "IntakeAgent"
    assert [h.name for h in intake.handoffs] == ["AnalysisAgent"]


def test_intake_owns_only_the_criteria_tool() -> None:
    intake = build_agents(_state())
    assert [t.name for t in intake.tools] == ["set_criteria"]


def test_analysis_agent_exposes_the_three_analysis_tools() -> None:
    analysis = build_agents(_state()).handoffs[0]
    assert set(t.name for t in analysis.tools) == {"rank_areas", "explain_area", "compare_areas"}


def test_instructions_carry_the_guardrails() -> None:
    intake = build_agents(_state())
    analysis = intake.handoffs[0]
    assert "23区" in intake.instructions or "23구" in intake.instructions
    assert "투자" in analysis.instructions
