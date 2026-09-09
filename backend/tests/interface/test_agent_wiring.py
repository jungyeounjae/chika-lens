"""에이전트 배선만 확인한다. LLM 호출은 하지 않는다."""

import pytest

pytest.importorskip("agents", reason="openai-agents 미설치 환경에서는 건너뛴다")

from chika.interface.agent.agents import build_agents  # noqa: E402


def test_entry_agent_is_intake_and_hands_off_to_analysis() -> None:
    intake = build_agents()
    assert intake.name == "IntakeAgent"
    assert [h.name for h in intake.handoffs] == ["AnalysisAgent"]


def test_intake_owns_only_the_criteria_tool() -> None:
    intake = build_agents()
    assert [t.name for t in intake.tools] == ["set_criteria"]


def test_analysis_agent_exposes_the_analysis_tools() -> None:
    """lookup_station 이 없으면 '히카리가오카 어때?' 같은 질문에 답할 수 없다 —
    explain_area 는 해시 id 를 요구하는데 이름을 id 로 바꿀 수단이 사라진다."""
    analysis = build_agents().handoffs[0]
    assert set(t.name for t in analysis.tools) == {
        "rank_areas",
        "lookup_station",
        "explain_area",
        "compare_areas",
        "metric_distribution",
    }


def test_instructions_carry_the_guardrails() -> None:
    intake = build_agents()
    analysis = intake.handoffs[0]
    assert "23区" in intake.instructions or "23구" in intake.instructions
    assert "투자" in analysis.instructions
