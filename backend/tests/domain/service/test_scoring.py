import pytest

from chika.domain.model.metrics import AreaMetrics, MetricKey
from chika.domain.model.weights import Weights
from chika.domain.service.scoring import rank, score


def _area(station_id: str, **percentiles: float) -> AreaMetrics:
    filled = {key: 50.0 for key in MetricKey}
    for name, value in percentiles.items():
        filled[MetricKey(name)] = value
    return AreaMetrics(station_id=station_id, percentile=filled, missing=frozenset())


def test_all_neutral_percentiles_score_50() -> None:
    result = score(_area("s1"), Weights.normalized({key: 1.0 for key in MetricKey}))
    assert result.total == pytest.approx(50.0)


def test_zero_weight_metric_does_not_affect_total() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    high = score(_area("s1", park=100.0), weights)
    low = score(_area("s2", park=0.0), weights)
    assert high.total == pytest.approx(low.total)


def test_contribution_is_weight_times_deviation_from_50() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    result = score(_area("s1", cafe=90.0), weights)
    assert result.contributions[MetricKey.CAFE] == pytest.approx(40.0)
    assert result.total == pytest.approx(90.0)


def test_low_percentile_pulls_the_total_down() -> None:
    weights = Weights.normalized({MetricKey.PRICE_LEVEL: 1.0})
    result = score(_area("s1", price_level=10.0), weights)
    assert result.total == pytest.approx(10.0)
    assert result.contributions[MetricKey.PRICE_LEVEL] < 0


def test_missing_flags_propagate_into_the_score() -> None:
    area = AreaMetrics(
        station_id="s1",
        percentile={key: 50.0 for key in MetricKey},
        missing=frozenset({MetricKey.KOREAN_GROCERY}),
    )
    result = score(area, Weights.normalized({MetricKey.CAFE: 1.0}))
    assert MetricKey.KOREAN_GROCERY in result.missing


def test_top_and_bottom_drivers_are_sorted_by_contribution() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0, MetricKey.PARK: 1.0, MetricKey.FITNESS: 1.0})
    result = score(_area("s1", cafe=100.0, park=0.0, fitness=60.0), weights)
    assert [key for key, _ in result.top_drivers(2)] == [MetricKey.CAFE, MetricKey.FITNESS]
    assert result.bottom_drivers(1)[0][0] == MetricKey.PARK


def test_rank_orders_by_total_descending() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    areas = [_area("mid", cafe=50.0), _area("top", cafe=99.0), _area("bot", cafe=1.0)]
    ranked = rank(areas, weights)
    assert [r.station_id for r in ranked] == ["top", "mid", "bot"]


def test_rank_breaks_ties_by_station_id_for_determinism() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    ranked = rank([_area("b", cafe=70.0), _area("a", cafe=70.0)], weights)
    assert [r.station_id for r in ranked] == ["a", "b"]


def test_score_stays_within_0_and_100() -> None:
    weights = Weights.normalized({key: 1.0 for key in MetricKey})
    best = score(_area("best", **{key.value: 100.0 for key in MetricKey}), weights)
    worst = score(_area("worst", **{key.value: 0.0 for key in MetricKey}), weights)
    assert best.total == pytest.approx(100.0)
    assert worst.total == pytest.approx(0.0)
