"""툴의 알맹이. LLM 없이 전부 단위 테스트된다.

가드레일은 프롬프트가 아니라 여기에 둔다 — 프롬프트에만 적으면 지켜지지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from chika.application.usecase.explain_area import MetricDetail
from chika.application.usecase.rank_areas import RankedArea
from chika.application.usecase.ward_price import WardPrice
from chika.domain.model.criteria import (
    HOUSEHOLD_LABELS_KO,
    Household,
    SearchCriteria,
)
from chika.domain.model.metrics import (
    METRIC_LABELS_KO,
    METRIC_UNITS,
    WARD_RESOLUTION_METRICS,
    MetricKey,
    display_raw_value,
)
from chika.domain.model.station import Station
from chika.domain.model.weights import DIAL_LABELS_KO, Dial, DialSettings, Weights
from chika.domain.service.dials import DIAL_TO_METRICS, expand_dials
from chika.domain.service.personas import seed_dials
from chika.interface.agent.state import SessionState

#: 구 랭킹에서 한 번에 낼 상한. 23구뿐이라 크게 잡을 이유가 없다.
MAX_WARD_LIMIT = 5

#: 실거래가와 정부 공시지가를 혼동하지 않도록 답변마다 못박는 문구.
PRICE_SOURCE_NOTE = (
    "MLIT 부동산 거래가격 정보 기준, 중고 맨션 실거래 ㎡당 단가의 중앙값입니다. "
    "정부가 고시하는 공시지가가 아닙니다."
)


def _missing(keys: Iterable[MetricKey]) -> list[dict[str, str]]:
    """결측 지표를 키와 이름으로. 키만 주면 서술에 키가 그대로 새어 나간다."""
    return [
        {"metric": key.value, "label": METRIC_LABELS_KO[key]} for key in sorted(keys)
    ]


def _interpretation(criteria: SearchCriteria) -> dict[str, Any]:
    """확정된 조건을 사람이 읽는 말로. 에이전트가 이것을 사용자에게 되읽어 준다.

    "신혼부부" 를 무엇으로 읽었는지 밝히지 않으면 사용자가 고칠 수 없다.
    프롬프트에 "해석을 설명하라"고만 적으면 LLM 이 해석을 **지어낸다** —
    실제로 적용된 값을 페이로드로 내려야 서술이 계산과 어긋나지 않는다.
    """
    return {
        "household": HOUSEHOLD_LABELS_KO[criteria.household],
        # 강도 0 인 축은 "보지 않는다"는 뜻이라 빼고 보낸다.
        "active_dials": [
            {"dial": dial.value, "label": DIAL_LABELS_KO[dial], "strength": strength}
            for dial in Dial
            if (strength := criteria.dials.strength(dial)) > 0
        ],
        "focus_metrics": sorted(
            {
                METRIC_LABELS_KO[key]
                for dial in Dial
                if criteria.dials.strength(dial) > 0
                for key in DIAL_TO_METRICS[dial]
            }
        ),
        # 지표 하나만 콕 집었을 때만 채워진다 — 이게 있으면 위 active_dials/
        # focus_metrics 는 무시되고 이 지표 하나에만 가중치 100%가 간다.
        "focus_metric": (
            METRIC_LABELS_KO[criteria.focus_metric]
            if criteria.focus_metric is not None
            else None
        ),
    }


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
    focus_metric: str | None = None,
) -> dict[str, Any]:
    """대화에서 모은 조건을 세션에 확정한다.

    **생략한 값은 이전 턴의 값을 유지한다** (스펙 §5.5, §2.2-2).

    전부 필수로 받으면 두 번째 턴이 첫 턴을 통째로 덮어쓴다. 실사용에서
    "한식당 많은 곳" 다음에 "통근지는 없어요"라고 답하자 한국 생활 강조가
    사라지고 전혀 다른 랭킹이 나왔다 — LLM은 그 턴에서 언급된 것만 넘기기 때문이다.

    **`focus_metric` 은 예외다 — 생략하면 이전 값을 유지하지 않고 `None`
    으로 돌아간다.** 다른 필드는 "누적되는 배경 조건"이지만 이건 "이번
    질문이 지표 하나만 콕 집은 것인가"라는 매 순간의 판단이다. 이전 턴에
    `park` 를 콕 집었다고 다음 턴에도 계속 `park` 만 보면, 사용자가 새로
    다른 조건을 물어도 계속 공원 하나로만 랭킹이 좁혀진다.
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

    focus_metric_key: MetricKey | None = None
    if focus_metric is not None:
        try:
            focus_metric_key = MetricKey(focus_metric)
        except ValueError:
            return {
                "error": "unknown_metric",
                "metric": focus_metric,
                "known_metrics": sorted(k.value for k in MetricKey),
            }

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

    spoken = {
        Dial.KOREAN_LIFE: dial(korean_life, Dial.KOREAN_LIFE),
        Dial.DAILY_CONVENIENCE: dial(daily_convenience, Dial.DAILY_CONVENIENCE),
        Dial.QUALITY_OF_LIFE: dial(quality_of_life, Dial.QUALITY_OF_LIFE),
        Dial.FAMILY: dial(family, Dial.FAMILY),
        Dial.COST_RISK: dial(cost_risk, Dial.COST_RISK),
    }
    # 가구 형태를 **이번 턴에 말했을 때만** 침묵한 축을 채운다. 매 턴 채우면
    # 사용자가 다이얼을 0 으로 되돌릴 방법이 없어진다.
    if household is not None:
        spoken = seed_dials(household_value, spoken)
    dials = DialSettings(spoken)
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
        focus_metric=focus_metric_key,
    )
    state.criteria = criteria
    state.last_ranking = []

    weights = (
        Weights({focus_metric_key: 1.0})
        if focus_metric_key is not None
        else expand_dials(dials)
    )
    return {
        "ok": True,
        "weights": {key.value: round(value, 4) for key, value in weights.items()},
        "budget_yen": budget,
        "household": household_value.value,
        # 적용된 해석. 서술이 이것과 다르면 계산과 어긋난 것이다.
        "interpretation": _interpretation(criteria),
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
            # 서술에 쓸 이름. 없으면 LLM 이 내부 키를 그대로 노출한다.
            "label": METRIC_LABELS_KO[key],
            "unit": METRIC_UNITS[key],
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
                "missing_metrics": _missing(row.score.missing),
            }
            for row in ranked
        ]
    }


def act_explain_area(state: SessionState, station_id: str) -> dict[str, Any]:
    """한 역을 지표별로 분해한다.

    **종합 점수는 이 역이 방금 만든 랭킹에 있을 때만 넘긴다.**

    종합 점수는 15지표의 가중 평균이라 프로필이 양극단인 동네를 평균으로
    뭉갠다. 光が丘(공원 백분위 99.2, 카페 9.3)은 균등 다이얼에서 39.9점인데
    육아 다이얼을 최대로 올려도 40.1점이다 — 다이얼에 거의 반응하지 않으면서
    "평균 이하"라는 인상만 남긴다. 게다가 지금은 15지표 중 3개가 결측이라
    점수의 20%가 50.0 자리채움이다.

    랭킹 안에서는 의미가 있다. 그 점수가 순서를 만들었고 비교 대상이 함께
    있기 때문이다. 반대로 "히카리가오카 육아하기 좋아?" 처럼 비교 기준 없이
    들어온 질문에서는 기준 없는 절대 점수가 되어 오해만 만든다.

    프롬프트로 "점수를 말하지 마"라고 적는 대신 페이로드에서 뺀다 — 보이면 쓴다.
    """
    if state.criteria is None:
        return {"error": "criteria_not_set", "message": "먼저 조건을 확정해야 합니다."}
    try:
        explanation = state.usecases.explain.execute(station_id, state.criteria)
    except KeyError:
        return {"error": "unknown_station", "station_id": station_id}

    in_ranking = any(row.station.id == station_id for row in state.last_ranking)

    def detail(item: MetricDetail) -> dict[str, Any]:
        return {
            "metric": item.key.value,
            "label": METRIC_LABELS_KO[item.key],
            # 단위가 없으면 LLM 이 raw_value 를 전부 개수로 읽는다.
            "unit": METRIC_UNITS[item.key],
            "percentile": round(item.percentile, 1),
            # 실제 개수. "공원 몇 개야?" 에 답하려면 백분위만으로는 부족하다.
            # 분수로 저장된 지표는 %로 옮겨 내보낸다 (`display_raw_value`).
            "raw_value": display_raw_value(item.key, item.raw_value),
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
        **(
            {"score": round(explanation.total, 1)}
            if in_ranking
            else {"score_omitted": "no_reference_set"}
        ),
        "rent_yen": explanation.rent_yen,
        # 이 분해가 어떤 조건으로 계산됐는지. "신혼부부에게 좋아?" 같은 질문은
        # 이 요약을 근거로 답한다 — 없으면 에이전트가 "판단할 데이터가 없다"고
        # 답하거나 측정하지 않은 특성을 지어낸다.
        "criteria": _interpretation(state.criteria),
        "strengths": [detail(item) for item in explanation.strengths],
        "weaknesses": [detail(item) for item in explanation.weaknesses],
        # 활성 다이얼마다 그 다이얼의 지표 전부. strengths/weaknesses(상위·
        # 하위 3개)에 없어도 여기서 확인한다 — "육아 환경을 함께 봤다"고
        # 말했으면 이 안에서 근거를 찾아 답에 넣는다.
        "by_dial": {
            dial.value: {
                "label": DIAL_LABELS_KO[dial],
                "metrics": [detail(item) for item in items],
            }
            for dial, items in explanation.by_dial.items()
        },
        "missing_metrics": _missing(explanation.missing),
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
                "label": METRIC_LABELS_KO[diff.key],
                "percentiles": {sid: round(p, 1) for sid, p in diff.percentiles.items()},
                "spread": round(diff.spread, 1),
            }
            for diff in comparison.differences
        ],
    }


def act_metric_distribution(state: SessionState, station_id: str, metric: str) -> dict[str, Any]:
    """한 지표를 주변 역 지도 색칠용으로 낸다.

    MLIT 서약(스펙 §3.1.2) 때문에 재해위험 등의 원본 Polygon은 지도에 못
    그린다 — 여기서 내는 값은 원본 구역이 아니라 우리가 정규화한 역 단위
    percentile 이므로 서약 밖이다. 조건(criteria)이 필요 없다 — 다이얼
    가중치가 아니라 지표 하나의 순수한 분포를 보는 것이라서다.
    """
    try:
        key = MetricKey(metric)
    except ValueError:
        return {
            "error": "unknown_metric",
            "metric": metric,
            "known_metrics": sorted(k.value for k in MetricKey),
        }

    try:
        points = state.usecases.distribution.execute(station_id, key)
    except KeyError:
        return {"error": "unknown_station", "station_id": station_id}

    return {
        "metric": key.value,
        "label": METRIC_LABELS_KO[key],
        "unit": METRIC_UNITS[key],
        "is_ward_resolution": key in WARD_RESOLUTION_METRICS,
        "points": [
            {
                "station_id": p.station.id,
                "name_ja": p.station.name_ja,
                "ward": p.station.ward,
                "lat": p.station.lat,
                "lon": p.station.lon,
                "percentile": round(p.percentile, 1),
                "raw_value": display_raw_value(key, p.raw_value),
                "is_missing": p.is_missing,
                "distance_m": round(p.distance_m),
            }
            for p in points
        ],
    }


def _ward_payload(w: WardPrice) -> dict[str, Any]:
    return {
        "ward": w.ward,
        "median_price": round(w.median_price, 1),
        "station_count": w.station_count,
        "representative": [
            {
                "station_id": r.station.id,
                "name_ja": r.station.name_ja,
                "lat": r.station.lat,
                "lon": r.station.lon,
                "price_level": round(r.price_level, 1),
                "price_percentile": round(r.price_percentile, 1),
                # 저평가 이유를 지어내지 말고 이 두 값으로만 말하라는
                # 근거 — "도심 거리" 같은 지표는 애초에 없다.
                "supermarket_percentile": round(r.supermarket_percentile, 1),
                "convenience_store_percentile": round(r.convenience_store_percentile, 1),
            }
            for r in w.representative
        ],
    }


def act_ward_price_ranking(
    state: SessionState,
    direction: str = "lowest",
    limit: int = 1,
    ward: str | None = None,
) -> dict[str, Any]:
    """구 단위 시세를 낸다 — 최저·최고 순위이거나, `ward` 를 주면 그 구 하나.

    "땅값이 가장 낮은/높은 구는 어디야?" 에는 direction/limit 로, "○○区
    시세는 어때?" 처럼 **특정 구**를 물으면 `ward` 로 답한다. `ward` 를 주면
    direction/limit 는 무시된다 — 최저 5·최고 5 순위에 없는 중간권 구(23개
    중 13개)는 direction 만으로는 아예 조회가 안 되기 때문이다.
    `rank_areas`는 다이얼 가중 종합점수이지 시세 순수 정렬이 아니라서,
    없는 정렬을 지어내는 대신 이 툴이 실제로 그 정렬·조회를 한다.
    """
    wards = state.usecases.ward_price.execute()
    if not wards:
        return {"error": "no_price_data"}

    if ward is not None:
        found = next((w for w in wards if w.ward == ward), None)
        if found is None:
            return {
                "error": "unknown_ward",
                "ward": ward,
                "known_wards": sorted(w.ward for w in wards),
            }
        selected = [found]
        direction = "single"
    else:
        if direction not in ("lowest", "highest"):
            return {"error": "unknown_direction", "direction": direction}
        capped = max(1, min(limit, MAX_WARD_LIMIT))
        selected = wards[:capped] if direction == "lowest" else list(reversed(wards))[:capped]

    return {
        "metric": MetricKey.PRICE_LEVEL.value,
        "label": METRIC_LABELS_KO[MetricKey.PRICE_LEVEL],
        "unit": METRIC_UNITS[MetricKey.PRICE_LEVEL],
        "source_note": PRICE_SOURCE_NOTE,
        "direction": direction,
        "wards": [_ward_payload(w) for w in selected],
    }


#: metric_extremes 한 번에 낼 상한. 489역 전체를 다 보여줄 이유가 없다.
MAX_EXTREMES_LIMIT = 10


def act_metric_extremes(
    state: SessionState, metric: str, direction: str = "worst", limit: int = 5
) -> dict[str, Any]:
    """489역 전체를 지표 하나로 정렬해 최악/최선 N곳을 낸다.

    "홍수가 잦은 곳은?", "치안이 나쁜 곳은?" 처럼 비교 기준(다이얼) 없이
    지표 하나만으로 극값을 물을 때 쓴다. `metric_distribution`은 한 역
    반경만, `rank_areas`는 다이얼 가중 종합점수만 낸다 — 어느 쪽도 이
    질문에 못 쓴다.

    **정렬은 이미 끝나 있다.** `direction="worst"`면 리스트가 이미
    percentile 오름차순(가장 나쁜 역이 0번)이다. 받은 순서를 그대로
    옮기면 된다 — raw_value 방향과 대조해서 다시 뒤집지 마세요. 그렇게
    하다가 안전한 역(percentile 90+)을 "위험한 축"이라고 답한 적이 있다.
    """
    try:
        key = MetricKey(metric)
    except ValueError:
        return {
            "error": "unknown_metric",
            "metric": metric,
            "known_metrics": sorted(k.value for k in MetricKey),
        }
    if direction not in ("worst", "best"):
        return {"error": "unknown_direction", "direction": direction}

    capped = max(1, min(limit, MAX_EXTREMES_LIMIT))
    points = state.usecases.extremes.execute(key, worst_first=direction == "worst", limit=capped)
    if not points:
        return {"error": "no_data", "metric": key.value}

    return {
        "metric": key.value,
        "label": METRIC_LABELS_KO[key],
        "unit": METRIC_UNITS[key],
        "is_ward_resolution": key in WARD_RESOLUTION_METRICS,
        "direction": direction,
        "points": [
            {
                "station_id": p.station.id,
                "name_ja": p.station.name_ja,
                "ward": p.station.ward,
                "lat": p.station.lat,
                "lon": p.station.lon,
                "percentile": round(p.percentile, 1),
                "raw_value": display_raw_value(key, p.raw_value),
            }
            for p in points
        ],
    }
