import pytest

from chika.domain.model.metrics import NEUTRAL_PERCENTILE, MetricKey, RawMetrics
from chika.domain.service.normalization import normalize, percentile_rank


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    """지정하지 않은 지표는 모두 0.0으로 채운다."""
    filled: dict[MetricKey, float | None] = {key: 0.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def test_percentile_rank_of_single_value_is_50() -> None:
    assert percentile_rank(7.0, [7.0]) == pytest.approx(50.0)


def test_percentile_rank_uses_mid_rank_for_ties() -> None:
    # 값 4개 중 1개가 아래, 2개가 동률 -> (1 + 0.5*2) / 4 = 50%
    assert percentile_rank(5.0, [1.0, 5.0, 5.0, 9.0]) == pytest.approx(50.0)


def test_percentile_rank_of_maximum_is_high() -> None:
    assert percentile_rank(9.0, [1.0, 5.0, 9.0]) == pytest.approx(100.0 * 2.5 / 3)


def test_positive_metric_higher_raw_gives_higher_percentile() -> None:
    areas = normalize(
        [
            _raw("low", cafe=1.0),
            _raw("high", cafe=100.0),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["high"].percentile[MetricKey.CAFE] > by_id["low"].percentile[MetricKey.CAFE]


def test_negative_metric_is_inverted() -> None:
    areas = normalize(
        [
            _raw("cheap", price_level=100_000.0),
            _raw("expensive", price_level=300_000.0),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["cheap"].percentile[MetricKey.PRICE_LEVEL] > (
        by_id["expensive"].percentile[MetricKey.PRICE_LEVEL]
    )


def test_missing_value_gets_neutral_percentile_and_a_flag() -> None:
    areas = normalize(
        [
            _raw("known", cafe=10.0),
            _raw("unknown", cafe=None),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["unknown"].percentile[MetricKey.CAFE] == NEUTRAL_PERCENTILE
    assert MetricKey.CAFE in by_id["unknown"].missing
    assert MetricKey.CAFE not in by_id["known"].missing


def test_missing_values_are_excluded_from_the_population() -> None:
    # cafe 관측치는 10.0 하나뿐 -> 그 하나는 percentile 50 이어야 한다
    areas = normalize([_raw("a", cafe=10.0), _raw("b", cafe=None), _raw("c", cafe=None)])
    by_id = {a.station_id: a for a in areas}
    assert by_id["a"].percentile[MetricKey.CAFE] == pytest.approx(NEUTRAL_PERCENTILE)


def test_metric_missing_everywhere_is_neutral_and_flagged_everywhere() -> None:
    areas = normalize([_raw("a", cafe=None), _raw("b", cafe=None)])
    for area in areas:
        assert area.percentile[MetricKey.CAFE] == NEUTRAL_PERCENTILE
        assert MetricKey.CAFE in area.missing


def test_input_order_is_preserved() -> None:
    areas = normalize([_raw("z"), _raw("a"), _raw("m")])
    assert [a.station_id for a in areas] == ["z", "a", "m"]


def test_normalize_of_empty_input_is_empty() -> None:
    assert normalize([]) == []
