import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.domain.model.criteria import Household
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
    act_rank_areas,
    act_set_criteria,
)
from chika.interface.agent.state import SessionState, UseCases


@pytest.fixture
def state() -> SessionState:
    stations, raws, commute, prices = build_seed(count=40)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
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


def test_rank_before_set_criteria_is_refused(state: SessionState) -> None:
    result = act_rank_areas(state)
    assert result["error"] == "criteria_not_set"
    assert result["areas"] == []


def test_rank_returns_scores_and_drivers(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_rank_areas(state, limit=3)
    assert len(result["areas"]) == 3
    first = result["areas"][0]
    assert set(first) >= {"station_id", "name_ko", "ward", "lat", "lon", "score", "top_drivers"}
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
