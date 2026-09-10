import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.metric_distribution import MetricDistribution
from chika.application.usecase.metric_extremes import MetricExtremes
from chika.application.usecase.rank_areas import RankAreas
from chika.application.usecase.ward_price import WardPriceRanking
from chika.domain.model.criteria import Household
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.actions import (
    act_compare_areas,
    act_explain_area,
    act_lookup_station,
    act_metric_distribution,
    act_metric_extremes,
    act_rank_areas,
    act_set_criteria,
    act_ward_price_ranking,
)
from chika.interface.agent.state import SessionState, UseCases


def _station(
    station_id: str, name_ja: str | None = None, ward: str = "中野区"
) -> Station:
    return Station(
        id=station_id,
        name_ja=name_ja or station_id,
        ward=ward,
        lat=35.70,
        lon=139.66,
        lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _deterministic_state(
    stations: list[Station],
    raws: list[RawMetrics],
    commute: dict[tuple[str, str], int] | None = None,
    prices: dict[str, int] | None = None,
) -> SessionState:
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(
                areas, FakeCommuteRepository(commute or {}), FakePriceRepository(prices or {})
            ),
            explain=ExplainArea(areas, FakePriceRepository(prices or {})),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
        )
    )


@pytest.fixture
def state() -> SessionState:
    stations, raws, commute, prices = build_seed(count=40)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
        )
    )


def _set_default_criteria(state: SessionState) -> dict:
    return act_set_criteria(
        state,
        korean_life=3.0,
        daily_convenience=2.0,
        quality_of_life=1.0,
        family=0.0,
        cost_risk=2.0,
    )


def test_set_criteria_stores_dials_on_the_session(state: SessionState) -> None:
    _set_default_criteria(state)
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 3.0
    assert state.criteria.dials.strength(Dial.FAMILY) == 0.0


def test_set_criteria_returns_the_expanded_weights_for_transparency(state: SessionState) -> None:
    result = _set_default_criteria(state)
    # 15개 가중치를 각각 4자리로 반올림하므로 합에 최대 7.5e-4의 오차가 쌓인다.
    # 정확한 합=1은 도메인의 책임이고 Task 3에서 검증된다 (test_expanded_weights_always_sum_to_one).
    # 여기서 확인하려는 것은 "가중치가 정규화되어 있다"는 성질이다.
    assert sum(result["weights"].values()) == pytest.approx(1.0, abs=1e-3)
    assert result["weights"]["korean_restaurant"] > result["weights"]["cafe"]


def test_set_criteria_accepts_budget_and_household(state: SessionState) -> None:
    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0, family=1.0, cost_risk=1.0,
        budget_min_yen=80_000, budget_max_yen=150_000, household="family",
    )
    assert state.criteria is not None
    assert state.criteria.budget_yen == (80_000, 150_000)
    assert state.criteria.household is Household.FAMILY


def test_set_criteria_rejects_an_unknown_household(state: SessionState) -> None:
    with pytest.raises(ValueError, match="household"):
        act_set_criteria(
            state,
            korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
            family=1.0, cost_risk=1.0, household="dormitory",
        )


def test_set_criteria_can_be_called_again_to_revise(state: SessionState) -> None:
    _set_default_criteria(state)
    act_set_criteria(
        state,
        korean_life=0.0, daily_convenience=0.0, quality_of_life=0.0, family=5.0, cost_risk=0.0,
        budget_max_yen=120_000,
    )
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.FAMILY) == 5.0
    assert state.criteria.budget_yen == (0, 120_000)


def test_set_criteria_accepts_a_focus_metric(state: SessionState) -> None:
    """"공원이 제일 많은 역은?" 처럼 지표 하나만 콕 집었을 때 쓴다."""
    result = act_set_criteria(state, focus_metric="park")
    assert state.criteria is not None
    assert state.criteria.focus_metric is MetricKey.PARK
    # 가중치가 park 하나에 100% 쏠린다 — quality_of_life 다이얼 균등분배가 아니다.
    assert result["weights"] == {"park": 1.0}
    assert result["interpretation"]["focus_metric"] == "공원"


def test_set_criteria_rejects_an_unknown_focus_metric(state: SessionState) -> None:
    result = act_set_criteria(state, focus_metric="not_a_metric")
    assert result["error"] == "unknown_metric"


def test_focus_metric_does_not_persist_across_turns(state: SessionState) -> None:
    """다른 필드(다이얼·예산 등)와 달리, 생략하면 이전 값이 아니라 None 으로
    돌아간다 — 이전 질문이 "공원만"이었다고 다음 질문까지 공원에 갇히면 안 된다."""
    act_set_criteria(state, focus_metric="park")
    act_set_criteria(state, korean_life=3.0)
    assert state.criteria is not None
    assert state.criteria.focus_metric is None


def test_rank_before_set_criteria_is_refused(state: SessionState) -> None:
    result = act_rank_areas(state)
    assert result["error"] == "criteria_not_set"
    assert result["areas"] == []


def test_rank_returns_scores_and_drivers(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_rank_areas(state, limit=3)
    assert len(result["areas"]) == 3
    first = result["areas"][0]
    assert set(first) >= {"station_id", "name_ja", "ward", "lat", "lon", "score", "top_drivers"}
    assert 0.0 <= first["score"] <= 100.0
    assert len(first["top_drivers"]) == 3


def test_rank_caps_the_limit_to_protect_the_context_window(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_rank_areas(state, limit=999)
    assert len(result["areas"]) <= 10


def test_rank_stores_the_result_for_follow_up_questions(state: SessionState) -> None:
    _set_default_criteria(state)
    act_rank_areas(state, limit=3)
    assert len(state.last_ranking) == 3


def test_explain_returns_strengths_weaknesses_and_ward_flag(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    station_id = ranked["areas"][0]["station_id"]
    result = act_explain_area(state, station_id)
    assert result["strengths"]
    assert result["weaknesses"]
    assert all("is_ward_resolution" in item for item in result["strengths"])


def test_explain_marks_ward_resolution_metrics(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    result = act_explain_area(state, ranked["areas"][0]["station_id"])
    details = result["strengths"] + result["weaknesses"]
    ratios = [d for d in details if d["metric"] == "korean_resident_ratio"]
    assert all(d["is_ward_resolution"] for d in ratios)


def test_every_metric_detail_carries_its_unit(state: SessionState) -> None:
    """단위가 없으면 LLM 이 raw_value 를 전부 개수로 읽는다.

    시세 1,100,000 이 "110만 곳", 한국 국적 비율 3.5 가 "3.5곳"이 된다.
    """
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    details = act_explain_area(state, ranked["areas"][0]["station_id"])
    items = details["strengths"] + details["weaknesses"]
    items += ranked["areas"][0]["top_drivers"]
    assert items
    for item in items:
        assert item["unit"], item

    units = {item["metric"]: item["unit"] for item in items}
    for metric, expected in (
        ("price_level", "엔/㎡"),
        ("korean_resident_ratio", "%"),
        ("restaurant_variety", "종"),
        ("park", "곳"),
    ):
        if metric in units:
            assert units[metric] == expected


def test_explain_gives_the_total_score_for_a_station_in_the_ranking(
    state: SessionState,
) -> None:
    """랭킹 안에서는 종합 점수가 순서를 만든 근거다 — "왜 여기가 1위야"에 필요하다."""
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    result = act_explain_area(state, ranked["areas"][0]["station_id"])
    assert result["score"] == ranked["areas"][0]["score"]
    assert "score_omitted" not in result


def test_explain_withholds_the_total_score_when_there_is_no_ranking(
    state: SessionState,
) -> None:
    """비교 기준 없이 한 동네만 물으면 종합 점수는 오해만 만든다.

    光が丘 실측: 균등 다이얼 39.9점, 육아 다이얼을 최대로 올려도 40.1점.
    다이얼에 반응하지 않으면서 "평균 이하"라는 인상만 남는다. 백분위는 그대로
    주고 종합 점수만 뺀다 — 프롬프트로 금지하면 결국 쓰게 된다.
    """
    _set_default_criteria(state)
    station_id = state.usecases.rank.known_stations()[0].id
    result = act_explain_area(state, station_id)
    assert "score" not in result
    assert result["score_omitted"] == "no_reference_set"
    # 근거는 그대로 남아야 한다. 숨기는 것이 아니라 뭉개지 않는 것이다.
    assert result["strengths"]
    assert all("percentile" in item for item in result["strengths"])
    assert all("raw_value" in item for item in result["strengths"])


def test_new_criteria_withdraw_a_previously_granted_score(state: SessionState) -> None:
    """조건이 바뀌면 랭킹이 무효가 된다. 옛 순위를 근거로 점수를 계속 주면 안 된다."""
    _set_default_criteria(state)
    station_id = act_rank_areas(state, limit=1)["areas"][0]["station_id"]
    assert "score" in act_explain_area(state, station_id)
    act_set_criteria(state, korean_life=5.0)
    assert "score" not in act_explain_area(state, station_id)


def test_explain_of_unknown_station_returns_an_error_not_an_exception(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_explain_area(state, "no_such_station")
    assert result["error"] == "unknown_station"


def test_compare_returns_only_the_differing_axes(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=3)
    ids = [area["station_id"] for area in ranked["areas"][:2]]
    result = act_compare_areas(state, ids)
    assert len(result["differences"]) <= 5
    spreads = [d["spread"] for d in result["differences"]]
    assert spreads == sorted(spreads, reverse=True)


def test_compare_needs_two_stations(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_compare_areas(state, ["seed_000"])
    assert result["error"] == "need_two_stations"


# --- Finding 1: 랭킹 결과의 top_drivers/missing_metrics에 정직성 플래그가 실려야 한다 ---


def test_rank_top_driver_carries_ward_resolution_flag() -> None:
    """korean_life 다이얼만 켜면 top_drivers는 korean_restaurant/korean_grocery/
    korean_resident_ratio 셋뿐이다. 그중 korean_resident_ratio는 구 단위이므로
    is_ward_resolution이 True여야 한다."""
    stations = [_station("a"), _station("b")]
    raws = [
        _raw("a", korean_restaurant=99.0, korean_grocery=9.0, korean_resident_ratio=0.05),
        _raw("b", korean_restaurant=1.0, korean_grocery=0.5, korean_resident_ratio=0.001),
    ]
    state = _deterministic_state(stations, raws)
    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=0.0, quality_of_life=0.0,
        family=0.0, cost_risk=0.0,
    )
    result = act_rank_areas(state, limit=2)
    first = result["areas"][0]
    assert first["station_id"] == "a"

    drivers_by_metric = {d["metric"]: d for d in first["top_drivers"]}
    assert "korean_resident_ratio" in drivers_by_metric
    for metric, driver in drivers_by_metric.items():
        assert {"metric", "contribution", "percentile", "top_percent", "is_ward_resolution",
                "is_missing"} <= set(driver)
        assert driver["is_ward_resolution"] == (metric == "korean_resident_ratio")
    assert drivers_by_metric["korean_resident_ratio"]["is_ward_resolution"] is True


def test_rank_surfaces_missing_metrics_per_station() -> None:
    stations = [_station("a"), _station("b")]
    raws = [
        _raw("a", healthcare=None),
        _raw("b"),
    ]
    state = _deterministic_state(stations, raws)
    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
        family=1.0, cost_risk=1.0,
    )
    result = act_rank_areas(state, limit=2)
    by_id = {area["station_id"]: area for area in result["areas"]}
    # 키만 주면 서술에 내부 키가 새어 나간다 — 이름을 함께 싣는다.
    assert by_id["a"]["missing_metrics"] == [
        {"metric": "healthcare", "label": "의료·약국"}
    ]
    assert by_id["b"]["missing_metrics"] == []


def test_rank_top_percent_is_100_minus_percentile() -> None:
    stations = [_station("a"), _station("b")]
    raws = [
        _raw("a", korean_restaurant=99.0, korean_grocery=9.0, korean_resident_ratio=0.05),
        _raw("b", korean_restaurant=1.0, korean_grocery=0.5, korean_resident_ratio=0.001),
    ]
    state = _deterministic_state(stations, raws)
    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=0.0, quality_of_life=0.0,
        family=0.0, cost_risk=0.0,
    )
    result = act_rank_areas(state, limit=2)
    first = result["areas"][0]
    for driver in first["top_drivers"]:
        assert driver["top_percent"] == pytest.approx(100 - driver["percentile"], abs=1e-9)


# --- Finding 2: commute_to는 반드시 실제 역으로 해석되어야 한다 ---


def test_set_criteria_rejects_an_unknown_commute_destination() -> None:
    stations = [_station("a"), _station("hub", name_ja="中心駅")]
    raws = [_raw("a"), _raw("hub")]
    state = _deterministic_state(stations, raws, commute={("a", "hub"): 10})

    result = act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
        family=1.0, cost_risk=1.0,
        commute_to="신주쿠", commute_max_minutes=30,
    )
    assert result["error"] == "unknown_commute_station"
    assert result["commute_to"] == "신주쿠"
    assert "candidates" in result
    assert state.criteria is None


def test_set_criteria_resolves_commute_destination_by_station_name() -> None:
    """LLM은 사용자가 말한 일본어 역명을 넘긴다. 저장되는 것은 해석된 id다."""
    stations = [_station("a"), _station("hub", name_ja="中心駅")]
    raws = [_raw("a"), _raw("hub")]

    state_id = _deterministic_state(stations, raws, commute={("a", "hub"): 10})
    act_set_criteria(
        state_id,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
        family=1.0, cost_risk=1.0,
        commute_to="hub", commute_max_minutes=30,
    )
    assert state_id.criteria is not None
    assert state_id.criteria.commute_to == "hub"

    state_ja = _deterministic_state(stations, raws, commute={("a", "hub"): 10})
    act_set_criteria(
        state_ja,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
        family=1.0, cost_risk=1.0,
        commute_to="中心駅", commute_max_minutes=30,
    )
    assert state_ja.criteria is not None
    assert state_ja.criteria.commute_to == "hub"


def test_resolved_commute_destination_actually_filters_the_ranking() -> None:
    stations = [
        _station("near"),
        _station("far"),
        _station("hub", name_ja="中心駅"),
    ]
    raws = [_raw("near"), _raw("far"), _raw("hub")]
    commute = {("near", "hub"): 10, ("far", "hub"): 55}
    state = _deterministic_state(stations, raws, commute=commute)

    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
        family=1.0, cost_risk=1.0,
        commute_to="中心駅", commute_max_minutes=30,
    )
    result = act_rank_areas(state, limit=10)
    ids = {area["station_id"] for area in result["areas"]}
    assert "far" not in ids
    assert "near" in ids
    assert "hub" in ids


# --- 조건 되돌리기 (스펙 §5.5) ---


def test_omitted_dials_keep_their_previous_values(state: SessionState) -> None:
    """실사용에서 드러난 결함: 두 번째 턴이 첫 턴의 조건을 통째로 지웠다.

    사용자가 "한식당이 많은 곳"이라 말한 뒤 "통근지는 없어요"라고만 답하면,
    LLM은 그 턴에서 언급된 것만 넘긴다. 다이얼을 필수로 받으면 한국 생활
    강조가 사라지고 전혀 다른 랭킹이 나온다.
    """
    act_set_criteria(state, korean_life=5.0, daily_convenience=1.0)
    act_set_criteria(state, household="single")

    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 5.0
    assert state.criteria.dials.strength(Dial.DAILY_CONVENIENCE) == 1.0


def test_a_named_dial_overwrites_only_itself(state: SessionState) -> None:
    act_set_criteria(state, korean_life=5.0, family=1.0)
    act_set_criteria(state, family=4.0)

    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 5.0
    assert state.criteria.dials.strength(Dial.FAMILY) == 4.0


def test_omitted_budget_and_household_are_kept(state: SessionState) -> None:
    act_set_criteria(
        state, korean_life=3.0, budget_max_yen=150_000, household="family"
    )
    act_set_criteria(state, quality_of_life=2.0)

    assert state.criteria is not None
    assert state.criteria.budget_yen == (0, 150_000)
    assert state.criteria.household is Household.FAMILY


def test_budget_can_be_revised(state: SessionState) -> None:
    """스펙 §2.2-2 — '예산 12만엔으로 낮추면?'"""
    act_set_criteria(state, korean_life=3.0, budget_max_yen=150_000)
    act_set_criteria(state, budget_max_yen=120_000)

    assert state.criteria is not None
    assert state.criteria.budget_yen == (0, 120_000)


def test_the_first_call_needs_no_previous_state(state: SessionState) -> None:
    act_set_criteria(state, korean_life=5.0)
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 5.0
    assert state.criteria.dials.strength(Dial.FAMILY) == 0.0


def test_revising_criteria_clears_the_stale_ranking(state: SessionState) -> None:
    act_set_criteria(state, korean_life=5.0)
    act_rank_areas(state, limit=3)
    act_set_criteria(state, family=5.0)
    assert state.last_ranking == []


# --- 역 이름으로 찾기 ---


def test_lookup_finds_a_station_by_japanese_name(state: SessionState) -> None:
    """실사용에서 드러난 구멍: '히카리가오카 어때?' 에 답할 방법이 없었다.

    explain_area 는 해시 id 를 요구하는데 에이전트는 이름을 id 로 바꿀 수단이
    없어, 랭킹 상위에 없는 역은 '데이터가 없다'고 답했다.
    """
    stations = [_station("a", name_ja="光が丘"), _station("b", name_ja="新宿")]
    state = _deterministic_state(stations, [_raw("a"), _raw("b")])
    result = act_lookup_station(state, "光が丘")
    assert result["matches"][0]["station_id"] == "a"
    assert result["matches"][0]["name_ja"] == "光が丘"


def test_lookup_matches_a_partial_name(state: SessionState) -> None:
    """사용자는 '히카리가오카'라고 쓰거나 역명 일부만 적는다."""
    stations = [_station("a", name_ja="光が丘"), _station("b", name_ja="新宿三丁目")]
    state = _deterministic_state(stations, [_raw("a"), _raw("b")])
    assert act_lookup_station(state, "新宿")["matches"][0]["station_id"] == "b"


def test_lookup_returns_every_candidate_when_ambiguous(state: SessionState) -> None:
    stations = [
        _station("a", name_ja="新宿"),
        _station("b", name_ja="新宿三丁目"),
        _station("c", name_ja="西新宿"),
    ]
    state = _deterministic_state(stations, [_raw("a"), _raw("b"), _raw("c")])
    assert len(act_lookup_station(state, "新宿")["matches"]) == 3


def test_an_exact_match_ranks_first(state: SessionState) -> None:
    stations = [_station("a", name_ja="新宿三丁目"), _station("b", name_ja="新宿")]
    state = _deterministic_state(stations, [_raw("a"), _raw("b")])
    assert act_lookup_station(state, "新宿")["matches"][0]["station_id"] == "b"


def test_lookup_of_an_unknown_name_returns_no_matches(state: SessionState) -> None:
    """0건과 '데이터 없음'은 다르다. 에이전트가 구분할 수 있어야 한다."""
    stations = [_station("a", name_ja="新宿")]
    state = _deterministic_state(stations, [_raw("a")])
    result = act_lookup_station(state, "横浜")
    assert result["matches"] == []
    assert "横浜" in result["query"]


def test_lookup_carries_the_ward_for_disambiguation(state: SessionState) -> None:
    stations = [_station("a", name_ja="光が丘", ward="練馬区")]
    state = _deterministic_state(stations, [_raw("a")])
    assert act_lookup_station(state, "光が丘")["matches"][0]["ward"] == "練馬区"


def test_lookup_caps_the_match_list(state: SessionState) -> None:
    stations = [_station(f"s{i}", name_ja=f"新宿{i}") for i in range(20)]
    state = _deterministic_state(stations, [_raw(f"s{i}") for i in range(20)])
    assert len(act_lookup_station(state, "新宿")["matches"]) <= 10


def test_explain_carries_coordinates_so_the_map_can_pin_it(state: SessionState) -> None:
    """지도가 rank_areas 에만 반응하면 '이 동네 어때?' 질문에서 화면 절반이 논다.

    explain_area 가 좌표를 주지 않으면 프론트는 핀을 찍을 수 없다.
    """
    stations = [_station("a", name_ja="光が丘", ward="練馬区")]
    state = _deterministic_state(stations, [_raw("a")])
    act_set_criteria(state, korean_life=1.0)
    result = act_explain_area(state, "a")
    assert result["lat"] == pytest.approx(35.70)
    assert result["lon"] == pytest.approx(139.66)


def test_explain_surfaces_nearby_stations_for_the_map(state: SessionState) -> None:
    """API 비용 0으로 '역이 하나뿐인 동네'를 지도에서 보여준다."""
    stations = [
        _station("center", name_ja="光が丘"),
        _station("near", name_ja="練馬春日町"),
    ]
    stations = [
        Station(id="center", name_ja="光が丘", ward="練馬区",
                lat=35.7594, lon=139.6299, lines=("大江戸線",)),
        Station(id="near", name_ja="練馬春日町", ward="練馬区",
                lat=35.7500, lon=139.6350, lines=("大江戸線",)),
    ]
    state = _deterministic_state(stations, [_raw("center"), _raw("near")])
    act_set_criteria(state, korean_life=1.0)
    result = act_explain_area(state, "center")

    assert result["nearby"][0]["name_ja"] == "練馬春日町"
    assert result["nearby"][0]["distance_m"] > 0
    assert result["nearby"][0]["lat"] == pytest.approx(35.7500)
    assert result["nearby"][0]["lines"] == ["大江戸線"]


# --- 페르소나 질문: "大久保는 신혼부부가 살기 좋은 동네야?" ---


def _persona_state() -> SessionState:
    return _deterministic_state(
        [_station("a"), _station("b"), _station("c")],
        [_raw("a"), _raw("b"), _raw("c")],
    )


def test_a_household_seeds_the_dials_it_implies(state: SessionState) -> None:
    """가구 형태를 말하면 침묵한 축이 채워져 점수가 실제로 움직인다.

    이전에는 `household` 가 월세 배수에만 쓰여, 실데이터(월세 없음)에서
    couple 로 바꿔도 랭킹이 한 칸도 움직이지 않았다.
    """
    act_set_criteria(state, household="couple")
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.FAMILY) > 0
    assert state.criteria.dials.strength(Dial.DAILY_CONVENIENCE) > 0


def test_a_household_does_not_overwrite_a_dial_the_user_set(state: SessionState) -> None:
    act_set_criteria(state, family=5.0)
    act_set_criteria(state, household="couple")
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.FAMILY) == 5.0


def test_a_household_keeps_an_earlier_unrelated_dial(state: SessionState) -> None:
    """"한식당 많은 곳" 다음에 "신혼부부예요" 가 오면 둘 다 반영돼야 한다."""
    act_set_criteria(state, korean_life=5.0)
    result = act_set_criteria(state, household="couple")
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 5.0
    labels = {dial["label"] for dial in result["interpretation"]["active_dials"]}
    assert {"한국 생활", "육아 환경"} <= labels


def test_seeding_happens_only_on_the_turn_the_household_is_given(
    state: SessionState,
) -> None:
    """매 턴 채우면 사용자가 다이얼을 0 으로 되돌릴 방법이 없어진다."""
    act_set_criteria(state, household="single")
    act_set_criteria(state, korean_life=5.0)
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.FAMILY) == 0.0


def test_the_interpretation_is_readable_not_internal_keys(state: SessionState) -> None:
    """"신혼부부" 를 무엇으로 읽었는지 밝히지 않으면 사용자가 고칠 수 없다."""
    interpretation = act_set_criteria(state, household="couple")["interpretation"]
    assert interpretation["household"] == "부부·2인 가구"
    assert "보육시설" in interpretation["focus_metrics"]
    assert all(dial["label"] != dial["dial"] for dial in interpretation["active_dials"])


def test_explain_carries_the_criteria_it_was_computed_with() -> None:
    """이것이 없으면 에이전트가 "판단할 데이터가 없다"고 답한다."""
    session = _persona_state()
    act_set_criteria(session, household="couple")
    detail = act_explain_area(session, "a")
    assert detail["criteria"]["household"] == "부부·2인 가구"
    assert "아이 동반 시설" in detail["criteria"]["focus_metrics"]


def test_a_dial_the_household_zeroes_is_absent_from_the_focus() -> None:
    """1인 가구에서 보육시설은 가중치 0 이라 근거로 들면 안 된다."""
    session = _persona_state()
    act_set_criteria(session, household="single")
    detail = act_explain_area(session, "a")
    assert "보육시설" not in detail["criteria"]["focus_metrics"]


def test_a_ratio_metric_is_reported_as_a_percentage() -> None:
    """실사용에서 "한국 국적 비율 0.025811%" 가 나갔다 — 실제 2.58% 다.

    저장값은 `한국 국적자 / 구 인구` 라 분수인데 단위만 "%" 였다.
    """
    session = _deterministic_state(
        [_station("a"), _station("b")],
        [
            _raw("a", korean_resident_ratio=0.025811),
            _raw("b", korean_resident_ratio=0.004858),
        ],
    )
    act_set_criteria(session, korean_life=5.0)
    detail = act_explain_area(session, "a")
    ratio = next(
        item
        for item in [*detail["strengths"], *detail["weaknesses"]]
        if item["metric"] == MetricKey.KOREAN_RESIDENT_RATIO.value
    )
    assert ratio["raw_value"] == 2.58
    assert ratio["unit"] == "%"


def test_a_count_metric_is_left_alone() -> None:
    """환산은 분수 지표에만 적용된다. 공원 68곳이 6800곳이 되면 안 된다."""
    session = _deterministic_state(
        [_station("a"), _station("b")],
        [_raw("a", park=68.0), _raw("b", park=3.0)],
    )
    act_set_criteria(session, quality_of_life=5.0)
    detail = act_explain_area(session, "a")
    park = next(
        item
        for item in [*detail["strengths"], *detail["weaknesses"]]
        if item["metric"] == MetricKey.PARK.value
    )
    assert park["raw_value"] == 68.0


# --- metric_distribution: 지도 색칠용 역 단위 분포 ---


def test_metric_distribution_returns_label_and_unit_from_the_domain() -> None:
    """지도 배지도 이 label 을 쓴다 — 내부 키가 새면 화면과 서술이 어긋난다."""
    session = _deterministic_state(
        [_station("a"), _station("b")],
        [_raw("a", disaster_risk=1.0), _raw("b", disaster_risk=0.2)],
    )
    result = act_metric_distribution(session, "a", "disaster_risk")
    assert result["label"] == "재해위험"
    assert result["unit"] == "지수(0~1, 클수록 위험)"


def test_metric_distribution_points_carry_percentile_and_raw_value() -> None:
    session = _deterministic_state(
        [_station("a"), _station("b")],
        [_raw("a", disaster_risk=1.0), _raw("b", disaster_risk=0.2)],
    )
    result = act_metric_distribution(session, "a", "disaster_risk")
    points_by_id = {p["station_id"]: p for p in result["points"]}
    assert points_by_id["a"]["raw_value"] == 1.0
    # disaster_risk 는 감점 지표라 raw 가 클수록 percentile 은 낮다 (규칙 1-2와 같은 방향).
    assert points_by_id["a"]["percentile"] < points_by_id["b"]["percentile"]


def test_metric_distribution_rejects_an_unknown_metric_key() -> None:
    """내부 키가 아닌 문자열(한국어 라벨 등)을 넘기면 명확히 실패해야 한다."""
    session = _deterministic_state([_station("a")], [_raw("a")])
    result = act_metric_distribution(session, "a", "재해위험")
    assert result["error"] == "unknown_metric"
    assert "disaster_risk" in result["known_metrics"]


def test_metric_distribution_rejects_an_unknown_station() -> None:
    session = _deterministic_state([_station("a")], [_raw("a")])
    result = act_metric_distribution(session, "ghost", "disaster_risk")
    assert result["error"] == "unknown_station"


def test_metric_distribution_does_not_require_criteria() -> None:
    """가중치가 필요 없다 — set_criteria 없이도 바로 부를 수 있어야 한다."""
    session = _deterministic_state([_station("a")], [_raw("a", park=5.0)])
    assert session.criteria is None
    result = act_metric_distribution(session, "a", "park")
    assert "error" not in result


# --- ward_price_ranking: 구 단위 시세 최저·최고 ---


def test_ward_price_ranking_carries_the_source_note() -> None:
    """공시지가와 혼동하지 않도록 답변 첫 문장에 밝힐 문구다."""
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=400_000.0)]
    )
    result = act_ward_price_ranking(session)
    assert "공시지가" in result["source_note"]
    assert "MLIT" in result["source_note"]


def test_ward_price_ranking_defaults_to_lowest() -> None:
    session = _deterministic_state(
        [_station("cheap", ward="足立区"), _station("pricey", ward="港区")],
        [_raw("cheap", price_level=400_000.0), _raw("pricey", price_level=1_500_000.0)],
    )
    result = act_ward_price_ranking(session)
    assert result["wards"][0]["ward"] == "足立区"


def test_ward_price_ranking_highest_reverses_the_order() -> None:
    session = _deterministic_state(
        [_station("cheap", ward="足立区"), _station("pricey", ward="港区")],
        [_raw("cheap", price_level=400_000.0), _raw("pricey", price_level=1_500_000.0)],
    )
    result = act_ward_price_ranking(session, direction="highest")
    assert result["wards"][0]["ward"] == "港区"


def test_ward_price_ranking_rejects_an_unknown_direction() -> None:
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=400_000.0)]
    )
    result = act_ward_price_ranking(session, direction="cheapest")
    assert result["error"] == "unknown_direction"


def test_ward_price_ranking_reports_no_data_rather_than_guessing() -> None:
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=None)]
    )
    result = act_ward_price_ranking(session)
    assert result["error"] == "no_price_data"


def test_ward_price_ranking_caps_the_limit() -> None:
    stations = [_station(f"s{i}", ward=f"구{i}") for i in range(10)]
    raws = [_raw(f"s{i}", price_level=float(i) * 100_000) for i in range(10)]
    session = _deterministic_state(stations, raws)
    result = act_ward_price_ranking(session, limit=999)
    assert len(result["wards"]) <= 5


def test_ward_price_ranking_representative_stations_carry_reasoning_material() -> None:
    """도심 거리 같은 지어낸 지표가 아니라 상업 밀도 percentile만 준다."""
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=400_000.0)]
    )
    result = act_ward_price_ranking(session)
    rep = result["wards"][0]["representative"][0]
    assert set(rep) >= {
        "station_id", "name_ja", "lat", "lon",
        "price_level", "price_percentile",
        "supermarket_percentile", "convenience_store_percentile",
    }


def test_ward_price_ranking_does_not_require_criteria() -> None:
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=400_000.0)]
    )
    assert session.criteria is None
    result = act_ward_price_ranking(session)
    assert "error" not in result


def test_ward_price_ranking_with_a_ward_returns_only_that_ward() -> None:
    """"中野区 시세는 어때?"에 무관한 구 데이터를 답한 적이 있다 — 그 재발 방지."""
    session = _deterministic_state(
        [_station("a", ward="足立区"), _station("b", ward="中野区")],
        [_raw("a", price_level=400_000.0), _raw("b", price_level=1_000_000.0)],
    )
    result = act_ward_price_ranking(session, ward="中野区")
    assert len(result["wards"]) == 1
    assert result["wards"][0]["ward"] == "中野区"


def test_ward_price_ranking_ward_ignores_direction_and_limit() -> None:
    session = _deterministic_state(
        [_station("a", ward="足立区"), _station("b", ward="中野区")],
        [_raw("a", price_level=400_000.0), _raw("b", price_level=1_000_000.0)],
    )
    result = act_ward_price_ranking(session, direction="highest", limit=5, ward="足立区")
    assert [w["ward"] for w in result["wards"]] == ["足立区"]


def test_ward_price_ranking_rejects_an_unknown_ward_with_known_wards() -> None:
    session = _deterministic_state(
        [_station("a", ward="足立区")], [_raw("a", price_level=400_000.0)]
    )
    result = act_ward_price_ranking(session, ward="가상구")
    assert result["error"] == "unknown_ward"
    assert "足立区" in result["known_wards"]


# --- metric_extremes: 489역 전체 최악/최선 (재현: "재해위험이 낮은 역") ---


def test_metric_extremes_worst_is_pre_sorted_worst_first() -> None:
    """LLM이 raw_value 방향을 다시 계산해 뒤집지 않도록, 결과 자체가
    이미 원하는 순서다."""
    session = _deterministic_state(
        [_station("safe"), _station("risky")],
        [_raw("safe", disaster_risk=0.1), _raw("risky", disaster_risk=1.0)],
    )
    result = act_metric_extremes(session, "disaster_risk", direction="worst")
    assert result["points"][0]["station_id"] == "risky"


def test_metric_extremes_best_reverses_order() -> None:
    session = _deterministic_state(
        [_station("safe"), _station("risky")],
        [_raw("safe", disaster_risk=0.1), _raw("risky", disaster_risk=1.0)],
    )
    result = act_metric_extremes(session, "disaster_risk", direction="best")
    assert result["points"][0]["station_id"] == "safe"


def test_metric_extremes_returns_label_and_unit() -> None:
    session = _deterministic_state([_station("a")], [_raw("a", disaster_risk=1.0)])
    result = act_metric_extremes(session, "disaster_risk")
    assert result["label"] == "재해위험"
    assert result["unit"] == "지수(0~1, 클수록 위험)"


def test_metric_extremes_rejects_an_unknown_metric() -> None:
    session = _deterministic_state([_station("a")], [_raw("a")])
    result = act_metric_extremes(session, "홍수")
    assert result["error"] == "unknown_metric"


def test_metric_extremes_rejects_an_unknown_direction() -> None:
    session = _deterministic_state([_station("a")], [_raw("a", disaster_risk=1.0)])
    result = act_metric_extremes(session, "disaster_risk", direction="lowest")
    assert result["error"] == "unknown_direction"


def test_metric_extremes_does_not_require_criteria() -> None:
    session = _deterministic_state([_station("a")], [_raw("a", disaster_risk=1.0)])
    assert session.criteria is None
    result = act_metric_extremes(session, "disaster_risk")
    assert "error" not in result
