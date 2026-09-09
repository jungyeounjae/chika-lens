"""Agents SDK 툴 어댑터. 로직은 actions.py 에만 있다."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from chika.interface.agent import actions
from chika.interface.agent.state import SessionState


@function_tool
def set_criteria(
    ctx: RunContextWrapper[SessionState],
    korean_life: float | None = None,
    daily_convenience: float | None = None,
    quality_of_life: float | None = None,
    family: float | None = None,
    cost_risk: float | None = None,
    commute_to: str | None = None,
    commute_max_minutes: int | None = None,
    budget_min_yen: int | None = None,
    budget_max_yen: int | None = None,
    household: str | None = None,
    exclude_wards: list[str] | None = None,
) -> dict[str, Any]:
    """사용자 조건을 확정한다. 다이얼 5개는 0~5의 상대 강도다.

    commute_to는 반드시 실제 역 이름(한국어/일본어) 또는 id여야 한다.
    unknown_commute_station 오류가 오면 후보를 사용자에게 되물어야 한다.
    """
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
        exclude_wards=exclude_wards or (),
    )


@function_tool
def lookup_station(ctx: RunContextWrapper[SessionState], name: str) -> dict[str, Any]:
    """역 이름으로 station_id 를 찾는다. explain_area·compare_areas 에 넘길 id 를 얻는다."""
    return actions.act_lookup_station(ctx.context, name)


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


@function_tool
def metric_distribution(
    ctx: RunContextWrapper[SessionState], station_id: str, metric: str
) -> dict[str, Any]:
    """한 역 주변의 지표 하나를 지도에 색칠할 재료로 낸다 (역 단위 percentile).

    사용자가 "지도로 보여줘", "주변은 어때" 처럼 한 지표의 공간적 분포를
    물을 때 쓴다. metric 은 내부 키(예: disaster_risk)다 — 모르면
    explain_area 로 먼저 확인한다.
    """
    return actions.act_metric_distribution(ctx.context, station_id, metric)


@function_tool
def ward_price_ranking(
    ctx: RunContextWrapper[SessionState],
    direction: str = "lowest",
    limit: int = 1,
    ward: str | None = None,
) -> dict[str, Any]:
    """구 단위 시세를 낸다 — 최저/최고 순위이거나, 특정 구 하나.

    "땅값/시세가 가장 낮은/높은 구는 어디야?" 에는 direction("lowest"
    또는 "highest")으로 답한다. **"○○区 시세는 어때?"처럼 특정 구를
    물으면 ward 인자에 그 구 이름(반드시 일본어, 예: "港区")을 넣는다** —
    direction/limit 만으로는 최저·최고 5위 밖의 중간권 구를 조회할 수
    없다. rank_areas 는 종합점수 순위라 이 질문에 쓸 수 없다.
    """
    return actions.act_ward_price_ranking(
        ctx.context, direction=direction, limit=limit, ward=ward
    )


@function_tool
def metric_extremes(
    ctx: RunContextWrapper[SessionState],
    metric: str,
    direction: str = "worst",
    limit: int = 5,
) -> dict[str, Any]:
    """489역 전체를 지표 하나로 정렬해 최악/최선 N곳을 낸다.

    "홍수가 잦은 곳은?", "치안이 나쁜 곳은?" 처럼 비교 기준 없이 지표
    하나만으로 극값을 물을 때 쓴다. direction 은 "worst" 또는 "best"다.
    결과는 이미 정렬돼 있다 — raw_value 를 보고 다시 순서를 뒤집지 않는다.
    """
    return actions.act_metric_extremes(ctx.context, metric=metric, direction=direction, limit=limit)
