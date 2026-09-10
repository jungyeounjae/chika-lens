from collections.abc import Mapping

import pytest

from chika.application.usecase.rank_areas import RankAreas
from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed


def _station(station_id: str, ward: str = "中野区") -> Station:
    return Station(
        id=station_id,
        name_ja=station_id,
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


def _usecase(
    stations: list[Station],
    raws: list[RawMetrics],
    commute: dict[tuple[str, str], int] | None = None,
    prices: dict[str, int] | None = None,
) -> RankAreas:
    return RankAreas(
        areas=FakeAreaMetricsRepository(stations, raws),
        commute=FakeCommuteRepository(commute or {}),
        prices=FakePriceRepository(prices or {}),
    )


def test_ranks_by_the_requested_dial() -> None:
    usecase = _usecase(
        [_station("kimchi"), _station("plain")],
        [_raw("kimchi", korean_restaurant=30.0), _raw("plain", korean_restaurant=0.0)],
    )
    result = usecase.execute(SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 1.0})))
    assert result[0].station.id == "kimchi"


def test_focus_metric_ignores_dials_and_ranks_by_that_metric_alone() -> None:
    """"공원이 제일 많은 역은?" 처럼 지표 하나만 콕 집으면, quality_of_life
    다이얼(카페·공원·피트니스·음식점다양성 균등분배)에 뭉개지면 안 된다."""
    usecase = _usecase(
        [_station("park_rich"), _station("cafe_rich")],
        [
            _raw("park_rich", park=50.0, cafe=0.0),
            _raw("cafe_rich", park=0.0, cafe=50.0),
        ],
    )
    criteria = SearchCriteria(
        dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0}),
        focus_metric=MetricKey.PARK,
    )
    result = usecase.execute(criteria)
    assert result[0].station.id == "park_rich"


def test_focus_metric_matches_the_percentile_exactly() -> None:
    """가중치가 지표 하나에 100% 쏠리면 score = percentile 이라, 결과
    순서가 metric_extremes(direction="best")와 정확히 같아야 한다 —
    에이전트가 실수로 rank_areas 를 불러도 답이 틀리지 않는 이유다."""
    usecase = _usecase(
        [_station("a"), _station("b"), _station("c")],
        [_raw("a", park=10.0), _raw("b", park=30.0), _raw("c", park=20.0)],
    )
    criteria = SearchCriteria(dials=DialSettings.balanced(), focus_metric=MetricKey.PARK)
    result = usecase.execute(criteria)
    assert [r.station.id for r in result] == ["b", "c", "a"]


def test_limit_caps_the_result_size() -> None:
    stations, raws, commute, prices = build_seed(count=40)
    result = _usecase(stations, raws, commute, prices).execute(
        SearchCriteria(dials=DialSettings.balanced()), limit=5
    )
    assert len(result) == 5


def test_excluded_ward_is_removed() -> None:
    usecase = _usecase(
        [_station("a", ward="新宿区"), _station("b", ward="中野区")],
        [_raw("a"), _raw("b")],
    )
    result = usecase.execute(
        SearchCriteria(dials=DialSettings.balanced(), exclude_wards=("新宿区",)), limit=10
    )
    assert [r.station.id for r in result] == ["b"]


def test_budget_filter_drops_stations_over_the_ceiling() -> None:
    usecase = _usecase(
        [_station("cheap"), _station("pricey")],
        [_raw("cheap"), _raw("pricey")],
        prices={"cheap": 100_000, "pricey": 300_000},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(),
            budget_yen=(0, 150_000),
            household=Household.SINGLE,
        ),
        limit=10,
    )
    assert [r.station.id for r in result] == ["cheap"]


def test_budget_filter_uses_household_adjusted_rent() -> None:
    usecase = _usecase(
        [_station("a")],
        [_raw("a")],
        prices={"a": 100_000},
    )
    criteria = SearchCriteria(dials=DialSettings.balanced(), budget_yen=(0, 150_000))
    assert len(usecase.execute(criteria, limit=10)) == 1
    family = criteria.replace(household=Household.FAMILY)  # 100_000 * 1.9 = 190_000
    assert usecase.execute(family, limit=10) == []


def test_commute_filter_drops_stations_over_the_limit() -> None:
    usecase = _usecase(
        [_station("near"), _station("far"), _station("hub")],
        [_raw("near"), _raw("far"), _raw("hub")],
        commute={("near", "hub"): 10, ("far", "hub"): 55},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(), commute_to="hub", commute_max_minutes=30
        ),
        limit=10,
    )
    assert {r.station.id for r in result} == {"near", "hub"}


def test_unknown_commute_is_kept_and_surfaced_as_none() -> None:
    usecase = _usecase(
        [_station("mystery"), _station("hub")],
        [_raw("mystery"), _raw("hub")],
        commute={},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(), commute_to="hub", commute_max_minutes=30
        ),
        limit=10,
    )
    by_id = {r.station.id: r for r in result}
    assert "mystery" in by_id
    assert by_id["mystery"].commute_minutes is None


def test_percentiles_are_computed_before_filtering() -> None:
    """예산 필터를 걸어도 남은 역의 점수는 전체 모집단 기준 그대로여야 한다."""
    stations = [_station("a"), _station("b"), _station("c")]
    raws = [_raw("a", cafe=1.0), _raw("b", cafe=50.0), _raw("c", cafe=99.0)]
    prices = {"a": 100_000, "b": 100_000, "c": 300_000}
    criteria = SearchCriteria(dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0}))

    unfiltered = {
        r.station.id: r.score.total
        for r in _usecase(stations, raws, prices=prices).execute(criteria, limit=10)
    }
    filtered = {
        r.station.id: r.score.total
        for r in _usecase(stations, raws, prices=prices).execute(
            criteria.replace(budget_yen=(0, 150_000)), limit=10
        )
    }
    assert set(filtered) == {"a", "b"}
    assert filtered["a"] == pytest.approx(unfiltered["a"])
    assert filtered["b"] == pytest.approx(unfiltered["b"])


def test_result_carries_rent_and_commute_for_display() -> None:
    usecase = _usecase(
        [_station("a"), _station("hub")],
        [_raw("a"), _raw("hub")],
        commute={("a", "hub"): 22},
        prices={"a": 120_000},
    )
    result = usecase.execute(
        SearchCriteria(dials=DialSettings.balanced(), commute_to="hub"), limit=10
    )
    row = next(r for r in result if r.station.id == "a")
    assert row.rent_yen == 120_000
    assert row.commute_minutes == 22


def test_ranking_is_deterministic_across_runs() -> None:
    stations, raws, commute, prices = build_seed(count=40)
    criteria = SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 2.0, Dial.COST_RISK: 1.0}))
    first = [r.station.id for r in _usecase(stations, raws, commute, prices).execute(criteria)]
    second = [r.station.id for r in _usecase(stations, raws, commute, prices).execute(criteria)]
    assert first == second


class _CountingPriceRepository:
    """호출 횟수를 세는 래퍼. 실제 어댑터에서는 1회 = 쿼리 1회다."""

    def __init__(self, table: dict[str, int]) -> None:
        self._inner = FakePriceRepository(table)
        self.calls = 0

    def median_rents(self, household: Household) -> Mapping[str, int]:
        self.calls += 1
        return self._inner.median_rents(household)


class _CountingCommuteRepository:
    def __init__(self, table: dict[tuple[str, str], int]) -> None:
        self._inner = FakeCommuteRepository(table)
        self.calls = 0

    def minutes_from_all(self, dest_station_id: str) -> Mapping[str, int]:
        self.calls += 1
        return self._inner.minutes_from_all(dest_station_id)


def test_repositories_are_queried_once_per_execute_not_once_per_station() -> None:
    """역 수에 비례해 조회하면 실제 어댑터에서 250 라운드트립이 된다."""
    stations, raws, commute, prices = build_seed(count=40)
    counting_prices = _CountingPriceRepository(prices)
    counting_commute = _CountingCommuteRepository(commute)
    usecase = RankAreas(
        areas=FakeAreaMetricsRepository(stations, raws),
        commute=counting_commute,
        prices=counting_prices,
    )

    usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(),
            commute_to=stations[0].id,
            commute_max_minutes=60,
            budget_yen=(0, 10_000_000),
        ),
        limit=10,
    )

    assert counting_prices.calls == 1
    assert counting_commute.calls == 1


def test_commute_repository_is_not_queried_without_a_destination() -> None:
    stations, raws, commute, prices = build_seed(count=10)
    counting_commute = _CountingCommuteRepository(commute)
    RankAreas(
        areas=FakeAreaMetricsRepository(stations, raws),
        commute=counting_commute,
        prices=FakePriceRepository(prices),
    ).execute(SearchCriteria(dials=DialSettings.balanced()), limit=10)

    assert counting_commute.calls == 0
