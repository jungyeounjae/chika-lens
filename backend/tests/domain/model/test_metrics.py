import pytest

from chika.domain.model.metrics import (
    METRIC_UNITS,
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


def test_every_metric_has_a_unit() -> None:
    """지표를 추가하고 단위를 잊으면 KeyError 가 아니라 여기서 걸린다.

    툴 페이로드가 METRIC_UNITS[key] 로 직접 조회하므로 빠지면 런타임에 터진다.
    """
    assert set(METRIC_UNITS) == set(MetricKey)


def test_the_price_unit_is_not_a_count() -> None:
    """지표 13 은 매매 ㎡당 단가다. 월세도, 개수도 아니다."""
    assert METRIC_UNITS[MetricKey.PRICE_LEVEL] == "엔/㎡"


def test_the_resident_ratio_unit_is_a_percentage() -> None:
    assert METRIC_UNITS[MetricKey.KOREAN_RESIDENT_RATIO] == "%"
