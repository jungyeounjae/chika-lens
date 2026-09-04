import pytest

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import DIAL_TO_METRICS, expand_dials


def test_every_metric_belongs_to_exactly_one_dial() -> None:
    covered = [metric for metrics in DIAL_TO_METRICS.values() for metric in metrics]
    assert sorted(covered) == sorted(MetricKey)


def test_dial_mapping_matches_spec() -> None:
    assert DIAL_TO_METRICS[Dial.KOREAN_LIFE] == (
        MetricKey.KOREAN_RESTAURANT,
        MetricKey.KOREAN_GROCERY,
        MetricKey.KOREAN_RESIDENT_RATIO,
    )
    assert DIAL_TO_METRICS[Dial.FAMILY] == (
        MetricKey.CHILDCARE_EDUCATION,
        MetricKey.GOOD_FOR_CHILDREN,
    )


def test_single_dial_spreads_evenly_over_its_metrics() -> None:
    weights = expand_dials(DialSettings({Dial.FAMILY: 1.0}))
    assert weights[MetricKey.CHILDCARE_EDUCATION] == pytest.approx(0.5)
    assert weights[MetricKey.GOOD_FOR_CHILDREN] == pytest.approx(0.5)
    assert weights[MetricKey.CAFE] == 0.0


def test_dial_strength_is_relative_not_absolute() -> None:
    a = expand_dials(DialSettings({Dial.FAMILY: 1.0, Dial.COST_RISK: 1.0}))
    b = expand_dials(DialSettings({Dial.FAMILY: 5.0, Dial.COST_RISK: 5.0}))
    for metric in MetricKey:
        assert a[metric] == pytest.approx(b[metric])


def test_expanded_weights_always_sum_to_one() -> None:
    weights = expand_dials(
        DialSettings({Dial.KOREAN_LIFE: 3.0, Dial.DAILY_CONVENIENCE: 1.0, Dial.COST_RISK: 2.0})
    )
    assert sum(v for _, v in weights.items()) == pytest.approx(1.0)


def test_all_dials_zero_falls_back_to_balanced() -> None:
    weights = expand_dials(DialSettings({dial: 0.0 for dial in Dial}))
    balanced = expand_dials(DialSettings.balanced())
    for metric in MetricKey:
        assert weights[metric] == pytest.approx(balanced[metric])
