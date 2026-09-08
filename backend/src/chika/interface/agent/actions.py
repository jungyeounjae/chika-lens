"""툴의 알맹이. LLM 없이 전부 단위 테스트된다.

가드레일은 프롬프트가 아니라 여기에 둔다 — 프롬프트에만 적으면 지켜지지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chika.application.usecase.explain_area import MetricDetail
from chika.application.usecase.rank_areas import RankedArea
from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.metrics import WARD_RESOLUTION_METRICS, MetricKey
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import expand_dials
from chika.interface.agent.state import SessionState

#: 한 번에 LLM에 넘기는 역의 상한. 컨텍스트 낭비와 서술 품질 저하를 막는다.
MAX_RANKING_LIMIT = 10

VALUE_GAP_DISCLAIMER = (
    "이 수치는 공개 데이터에 기반한 통계적 추정이며 투자 조언이 아닙니다. "
    "실제 계약 전에는 반드시 현장과 중개사를 통해 확인하세요."
)


def _resolve_commute_station(commute_to: str, stations: Sequence[Station]) -> Station | None:
    """통근지 이름(한국어/일본어/id)을 역으로 해석한다. 못 찾으면 None."""
    for station in stations:
        if commute_to in (station.id, station.name_ja):
            return station
    return None


def act_set_criteria(
    state: SessionState,
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
    exclude_wards: Sequence[str] | None = None,
) -> dict[str, Any]:
    """대화에서 모은 조건을 세션에 확정한다.

    **생략한 값은 이전 턴의 값을 유지한다** (스펙 §5.5, §2.2-2).

    전부 필수로 받으면 두 번째 턴이 첫 턴을 통째로 덮어쓴다. 실사용에서
    "한식당 많은 곳" 다음에 "통근지는 없어요"라고 답하자 한국 생활 강조가
    사라지고 전혀 다른 랭킹이 나왔다 — LLM은 그 턴에서 언급된 것만 넘기기 때문이다.
    """
    previous = state.criteria

    if household is None:
        household_value = previous.household if previous else Household.SINGLE
    else:
        try:
            household_value = Household(household)
        except ValueError as exc:
            raise ValueError(
                f"unknown household: {household!r} (single/couple/family 중 하나)"
            ) from exc

    resolved_commute_to = previous.commute_to if previous else None
    if commute_to is not None:
        known_stations = state.usecases.rank.known_stations()
        station = _resolve_commute_station(commute_to, known_stations)
        if station is None:
            return {
                "error": "unknown_commute_station",
                "commute_to": commute_to,
                "candidates": [s.name_ja for s in known_stations[:5]],
            }
        resolved_commute_to = station.id

    budget: tuple[int, int] | None = previous.budget_yen if previous else None
    if budget_min_yen is not None or budget_max_yen is not None:
        budget = (budget_min_yen or 0, budget_max_yen or 10_000_000)

    def dial(given: float | None, key: Dial) -> float:
        if given is not None:
            return given
        return previous.dials.strength(key) if previous else 0.0

    dials = DialSettings(
        {
            Dial.KOREAN_LIFE: dial(korean_life, Dial.KOREAN_LIFE),
            Dial.DAILY_CONVENIENCE: dial(daily_convenience, Dial.DAILY_CONVENIENCE),
            Dial.QUALITY_OF_LIFE: dial(quality_of_life, Dial.QUALITY_OF_LIFE),
            Dial.FAMILY: dial(family, Dial.FAMILY),
            Dial.COST_RISK: dial(cost_risk, Dial.COST_RISK),
        }
    )
    criteria = SearchCriteria(
        dials=dials,
        commute_to=resolved_commute_to,
        commute_max_minutes=(
            commute_max_minutes
            if commute_max_minutes is not None
            else (previous.commute_max_minutes if previous else None)
        ),
        budget_yen=budget,
        household=household_value,
        exclude_wards=(
            tuple(exclude_wards)
            if exclude_wards is not None
            else (previous.exclude_wards if previous else ())
        ),
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


#: 후보가 많아도 LLM 컨텍스트를 채우지 않도록 자른다.
MAX_LOOKUP_MATCHES = 10


def act_lookup_station(state: SessionState, name: str) -> dict[str, Any]:
    """역 이름으로 station_id 를 찾는다.

    explain_area 는 해시 id 를 요구하는데, 사용자는 "히카리가오카 어때?" 라고
    이름으로 묻는다. 이 툴이 없으면 에이전트는 랭킹 상위에 없는 역에 대해
    "데이터가 없다"고 답한다 — 실제로는 있는데도.

    부분 일치를 허용하고 정확히 일치하는 것을 먼저 둔다. "新宿" 은 新宿·
    新宿三丁目·西新宿 을 모두 부르지만, 사용자가 뜻한 것은 대개 정확히 일치하는 쪽이다.
    """
    query = name.strip()
    if not query:
        return {"query": name, "matches": []}

    matched = [
        station
        for station in state.usecases.rank.known_stations()
        if query in station.name_ja
    ]
    matched.sort(key=lambda s: (s.name_ja != query, len(s.name_ja), s.id))

    return {
        "query": query,
        "matches": [
            {
                "station_id": station.id,
                "name_ja": station.name_ja,
                "ward": station.ward,
                "lines": list(station.lines),
            }
            for station in matched[:MAX_LOOKUP_MATCHES]
        ],
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

    commute_active = state.criteria.commute_to is not None

    def driver(key: MetricKey, contribution: float, row: RankedArea) -> dict[str, Any]:
        percentile = row.percentile[key]
        return {
            "metric": key.value,
            "contribution": round(contribution, 2),
            "percentile": round(percentile, 1),
            "top_percent": round(100 - percentile, 1),
            "is_ward_resolution": key in WARD_RESOLUTION_METRICS,
            "is_missing": key in row.score.missing,
        }

    return {
        "areas": [
            {
                "station_id": row.station.id,
                "name_ja": row.station.name_ja,
                "ward": row.station.ward,
                "lat": row.station.lat,
                "lon": row.station.lon,
                "score": round(row.score.total, 1),
                "rent_yen": row.rent_yen,
                "commute_minutes": row.commute_minutes,
                "commute_uncertain": commute_active and row.commute_minutes is None,
                "top_drivers": [
                    driver(key, value, row) for key, value in row.score.top_drivers(3)
                ],
                "missing_metrics": sorted(key.value for key in row.score.missing),
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

    def detail(item: MetricDetail) -> dict[str, Any]:
        return {
            "metric": item.key.value,
            "percentile": round(item.percentile, 1),
            # 실제 개수. "공원 몇 개야?" 에 답하려면 백분위만으로는 부족하다.
            "raw_value": item.raw_value,
            "contribution": round(item.contribution, 2),
            "is_missing": item.is_missing,
            "is_ward_resolution": item.is_ward_resolution,
        }

    return {
        "station_id": explanation.station.id,
        "name_ja": explanation.station.name_ja,
        "ward": explanation.station.ward,
        # 프론트가 지도에 핀을 찍는 재료. 없으면 특정 지역 조회에서 지도가 논다.
        "lat": explanation.station.lat,
        "lon": explanation.station.lon,
        "score": round(explanation.total, 1),
        "rent_yen": explanation.rent_yen,
        "strengths": [detail(item) for item in explanation.strengths],
        "weaknesses": [detail(item) for item in explanation.weaknesses],
        "missing_metrics": [key.value for key in explanation.missing],
        # 주변 역. 좌표가 로컬에 있어 API 비용이 0이다 —
        # 역이 하나뿐인 동네와 노선이 겹치는 동네의 차이를 지도가 보여준다.
        "nearby": [
            {
                "station_id": item.station.id,
                "name_ja": item.station.name_ja,
                "ward": item.station.ward,
                "lat": item.station.lat,
                "lon": item.station.lon,
                "lines": list(item.station.lines),
                "distance_m": round(item.distance_m),
            }
            for item in explanation.nearby
        ],
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
            {"station_id": s.id, "name_ja": s.name_ja, "ward": s.ward}
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
