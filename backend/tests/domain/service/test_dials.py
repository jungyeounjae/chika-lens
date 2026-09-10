import pytest

from chika.domain.model.metrics import DIRECTIONLESS_METRICS, HAZARD_LAYER_METRICS, MetricKey
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import DIAL_TO_METRICS, expand_dials


def test_every_scored_metric_belongs_to_exactly_one_dial() -> None:
    """레이어별 진단용 지표(HAZARD_LAYER_METRICS)와 유동인구
    (DIRECTIONLESS_METRICS)는 예외다 — 전자는 disaster_risk 와 중복
    반영을 막으려, 후자는 애초에 방향이 없어서 일부러 뺐다."""
    covered = [metric for metrics in DIAL_TO_METRICS.values() for metric in metrics]
    scored_metrics = set(MetricKey) - set(HAZARD_LAYER_METRICS) - set(DIRECTIONLESS_METRICS)
    assert sorted(covered) == sorted(scored_metrics)


def test_dial_mapping_matches_spec() -> None:
    assert DIAL_TO_METRICS[Dial.KOREAN_LIFE] == (
        MetricKey.KOREAN_RESTAURANT,
        MetricKey.KOREAN_GROCERY,
        MetricKey.KOREAN_RESIDENT_RATIO,
    )
    assert DIAL_TO_METRICS[Dial.FAMILY] == (
        MetricKey.CHILDCARE_EDUCATION,
        MetricKey.CHILD_FRIENDLY_VENUE,
        MetricKey.ELEMENTARY_SCHOOL,
        MetricKey.MIDDLE_SCHOOL,
    )


def test_single_dial_spreads_evenly_over_its_metrics() -> None:
    weights = expand_dials(DialSettings({Dial.FAMILY: 1.0}))
    assert weights[MetricKey.CHILDCARE_EDUCATION] == pytest.approx(0.25)
    assert weights[MetricKey.CHILD_FRIENDLY_VENUE] == pytest.approx(0.25)
    assert weights[MetricKey.ELEMENTARY_SCHOOL] == pytest.approx(0.25)
    assert weights[MetricKey.MIDDLE_SCHOOL] == pytest.approx(0.25)
    assert weights[MetricKey.CAFE] == 0.0


def test_large_retail_shares_the_daily_convenience_dial() -> None:
    """光が丘처럼 슈퍼가 적어도 복합몰이 있으면 daily_convenience 가 이걸
    반영해야 한다(스펙 §11-10) — supermarket 과 같은 다이얼에 넣었다."""
    assert MetricKey.LARGE_RETAIL in DIAL_TO_METRICS[Dial.DAILY_CONVENIENCE]
    weights = expand_dials(DialSettings({Dial.DAILY_CONVENIENCE: 1.0}))
    assert weights[MetricKey.LARGE_RETAIL] == pytest.approx(0.25)


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
