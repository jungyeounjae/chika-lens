import pytest

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings, Weights


def test_weights_normalize_to_one() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 3.0, MetricKey.PARK: 1.0})
    assert weights[MetricKey.CAFE] == pytest.approx(0.75)
    assert weights[MetricKey.PARK] == pytest.approx(0.25)
    assert sum(v for _, v in weights.items()) == pytest.approx(1.0)


def test_unlisted_metric_has_zero_weight() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    assert weights[MetricKey.DISASTER_RISK] == 0.0


def test_all_zero_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to zero"):
        Weights.normalized({MetricKey.CAFE: 0.0})


def test_negative_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative weight"):
        Weights.normalized({MetricKey.CAFE: -1.0})


def test_there_are_exactly_5_dials() -> None:
    assert len(Dial) == 5


def test_balanced_dial_settings_are_all_equal() -> None:
    settings = DialSettings.balanced()
    assert set(settings.values) == set(Dial)
    assert len(set(settings.values.values())) == 1
