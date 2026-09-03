import pytest

from chika.domain.model.metrics import (
    NEGATIVE_METRICS,
    WARD_RESOLUTION_METRICS,
    AreaMetrics,
    MetricKey,
    RawMetrics,
)


def test_there_are_exactly_15_metrics() -> None:
    assert len(MetricKey) == 15


def test_negative_metrics_are_the_three_penalty_axes() -> None:
    assert NEGATIVE_METRICS == frozenset(
        {MetricKey.PRICE_LEVEL, MetricKey.DISASTER_RISK, MetricKey.NUISANCE_VENUE}
    )


def test_ward_resolution_metric_is_flagged() -> None:
    assert MetricKey.KOREAN_RESIDENT_RATIO in WARD_RESOLUTION_METRICS
    assert MetricKey.KOREAN_RESTAURANT not in WARD_RESOLUTION_METRICS


def test_raw_metrics_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        RawMetrics(station_id="s1", values={"not_a_metric": 1.0})  # type: ignore[dict-item]


def test_area_metrics_requires_all_15_percentiles() -> None:
    with pytest.raises(ValueError, match="missing percentile"):
        AreaMetrics(
            station_id="s1",
            percentile={MetricKey.CAFE: 50.0},
            missing=frozenset(),
        )


def test_area_metrics_reports_ward_resolution() -> None:
    area = AreaMetrics(
        station_id="s1",
        percentile={key: 50.0 for key in MetricKey},
        missing=frozenset(),
    )
    assert area.is_ward_resolution(MetricKey.KOREAN_RESIDENT_RATIO) is True
    assert area.is_ward_resolution(MetricKey.CAFE) is False
