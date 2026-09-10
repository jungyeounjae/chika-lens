"""에이전트 2개 + in-process 핸드오프 (스펙 §5.2). A2A가 아니다.

지시문(프롬프트) 원문은 `prompts.py`에 있다 — 여기는 배선(어떤 에이전트가
어떤 툴을 갖는지, 핸드오프 구조)만 담당한다.
"""

from __future__ import annotations

from agents import Agent

from chika.interface.agent.prompts import ANALYSIS_INSTRUCTIONS, INTAKE_INSTRUCTIONS
from chika.interface.agent.state import SessionState
from chika.interface.agent.tools import (
    compare_areas,
    explain_area,
    lookup_station,
    metric_distribution,
    metric_extremes,
    rank_areas,
    set_criteria,
    ward_price_ranking,
)


def build_agents() -> Agent[SessionState]:
    """진입 에이전트(IntakeAgent)를 반환한다. state는 Runner.run(context=...)로 넘긴다."""
    analysis: Agent[SessionState] = Agent(
        name="AnalysisAgent",
        instructions=ANALYSIS_INSTRUCTIONS,
        tools=[
            rank_areas,
            lookup_station,
            explain_area,
            compare_areas,
            metric_distribution,
            ward_price_ranking,
            metric_extremes,
        ],
    )
    intake: Agent[SessionState] = Agent(
        name="IntakeAgent",
        instructions=INTAKE_INSTRUCTIONS,
        tools=[set_criteria],
        handoffs=[analysis],
    )
    return intake
