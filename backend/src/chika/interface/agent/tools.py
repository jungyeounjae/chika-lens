"""Agents SDK 툴 어댑터. 로직은 actions.py 에만 있다."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from chika.interface.agent import actions
from chika.interface.agent.state import SessionState


@function_tool
def set_criteria(
    ctx: RunContextWrapper[SessionState],
    korean_life: float,
    daily_convenience: float,
    quality_of_life: float,
    family: float,
    cost_risk: float,
    commute_to: str | None = None,
    commute_max_minutes: int | None = None,
    budget_min_yen: int | None = None,
    budget_max_yen: int | None = None,
    household: str = "single",
) -> dict[str, Any]:
    """사용자 조건을 확정한다. 다이얼 5개는 0~5의 상대 강도다."""
    return actions.act_set_criteria(
        ctx.context,
        korean_life=korean_life,
        daily_convenience=daily_convenience,
        quality_of_life=quality_of_life,
        family=family,
        cost_risk=cost_risk,
        commute_to=commute_to,
        commute_max_minutes=commute_max_minutes,
        budget_min_yen=budget_min_yen,
        budget_max_yen=budget_max_yen,
        household=household,
    )


@function_tool
def rank_areas(ctx: RunContextWrapper[SessionState], limit: int = 5) -> dict[str, Any]:
    """확정된 조건으로 역세권을 점수화해 상위 N곳을 반환한다."""
    return actions.act_rank_areas(ctx.context, limit=limit)


@function_tool
def explain_area(ctx: RunContextWrapper[SessionState], station_id: str) -> dict[str, Any]:
    """한 역의 점수를 지표별 기여도로 분해한다."""
    return actions.act_explain_area(ctx.context, station_id)


@function_tool
def compare_areas(
    ctx: RunContextWrapper[SessionState], station_ids: list[str]
) -> dict[str, Any]:
    """두 곳 이상을 비교해 차이 나는 축만 반환한다."""
    return actions.act_compare_areas(ctx.context, station_ids)
