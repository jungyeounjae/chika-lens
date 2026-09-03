"""툴의 알맹이. LLM 없이 전부 단위 테스트된다.

가드레일은 프롬프트가 아니라 여기에 둔다 — 프롬프트에만 적으면 지켜지지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import expand_dials
from chika.interface.agent.state import SessionState

#: 한 번에 LLM에 넘기는 역의 상한. 컨텍스트 낭비와 서술 품질 저하를 막는다.
MAX_RANKING_LIMIT = 10

VALUE_GAP_DISCLAIMER = (
    "이 수치는 공개 데이터에 기반한 통계적 추정이며 투자 조언이 아닙니다. "
    "실제 계약 전에는 반드시 현장과 중개사를 통해 확인하세요."
)


def act_set_criteria(
    state: SessionState,
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
    exclude_wards: Sequence[str] = (),
) -> dict[str, Any]:
    """대화에서 모은 조건을 세션에 확정한다. 다시 불러 일부만 바꿔도 된다."""
    try:
        household_value = Household(household)
    except ValueError as exc:
        raise ValueError(
            f"unknown household: {household!r} (single/couple/family 중 하나)"
        ) from exc

    budget: tuple[int, int] | None = None
    if budget_min_yen is not None or budget_max_yen is not None:
        budget = (budget_min_yen or 0, budget_max_yen or 10_000_000)

    dials = DialSettings(
        {
            Dial.KOREAN_LIFE: korean_life,
            Dial.DAILY_CONVENIENCE: daily_convenience,
            Dial.QUALITY_OF_LIFE: quality_of_life,
            Dial.FAMILY: family,
            Dial.COST_RISK: cost_risk,
        }
    )
    criteria = SearchCriteria(
        dials=dials,
        commute_to=commute_to,
        commute_max_minutes=commute_max_minutes,
        budget_yen=budget,
        household=household_value,
        exclude_wards=tuple(exclude_wards),
    )
    state.criteria = criteria
    state.last_ranking = []

    weights = expand_dials(dials)
    return {
        "ok": True,
        "weights": {key.value: round(value, 4) for key, value in weights.items()},
        "budget_yen": budget,
        "household": household_value.value,
    }


def act_rank_areas(state: SessionState, limit: int = 5) -> dict[str, Any]:
    if state.criteria is None:
        return {
            "error": "criteria_not_set",
            "message": "먼저 set_criteria로 조건을 확정해야 합니다.",
            "areas": [],
        }

    capped = max(1, min(limit, MAX_RANKING_LIMIT))
    ranked = state.usecases.rank.execute(state.criteria, limit=capped)
    state.last_ranking = ranked

    return {
        "areas": [
            {
                "station_id": row.station.id,
                "name_ko": row.station.name_ko,
                "name_ja": row.station.name_ja,
                "ward": row.station.ward,
                "lat": row.station.lat,
                "lon": row.station.lon,
                "score": round(row.score.total, 1),
                "rent_yen": row.rent_yen,
                "commute_minutes": row.commute_minutes,
                "top_drivers": [
                    {"metric": key.value, "contribution": round(value, 2)}
                    for key, value in row.score.top_drivers(3)
                ],
            }
            for row in ranked
        ]
    }


def act_explain_area(state: SessionState, station_id: str) -> dict[str, Any]:
    if state.criteria is None:
        return {"error": "criteria_not_set", "message": "먼저 조건을 확정해야 합니다."}
    try:
        explanation = state.usecases.explain.execute(station_id, state.criteria)
    except KeyError:
        return {"error": "unknown_station", "station_id": station_id}

    def detail(item: Any) -> dict[str, Any]:
        return {
            "metric": item.key.value,
            "percentile": round(item.percentile, 1),
            "contribution": round(item.contribution, 2),
            "is_missing": item.is_missing,
            "is_ward_resolution": item.is_ward_resolution,
        }

    return {
        "station_id": explanation.station.id,
        "name_ko": explanation.station.name_ko,
        "ward": explanation.station.ward,
        "score": round(explanation.total, 1),
        "rent_yen": explanation.rent_yen,
        "strengths": [detail(item) for item in explanation.strengths],
        "weaknesses": [detail(item) for item in explanation.weaknesses],
        "missing_metrics": [key.value for key in explanation.missing],
    }


def act_compare_areas(state: SessionState, station_ids: Sequence[str]) -> dict[str, Any]:
    if state.criteria is None:
        return {"error": "criteria_not_set", "message": "먼저 조건을 확정해야 합니다."}
    if len(station_ids) < 2:
        return {"error": "need_two_stations", "station_ids": list(station_ids)}
    try:
        comparison = state.usecases.compare.execute(station_ids, state.criteria)
    except KeyError as exc:
        return {"error": "unknown_station", "detail": str(exc)}

    return {
        "stations": [
            {"station_id": s.id, "name_ko": s.name_ko, "ward": s.ward}
            for s in comparison.stations
        ],
        "totals": {sid: round(total, 1) for sid, total in comparison.totals.items()},
        "differences": [
            {
                "metric": diff.key.value,
                "percentiles": {sid: round(p, 1) for sid, p in diff.percentiles.items()},
                "spread": round(diff.spread, 1),
            }
            for diff in comparison.differences
        ],
    }
