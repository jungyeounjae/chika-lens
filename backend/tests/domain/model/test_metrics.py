import pytest

from chika.domain.model.metrics import (
    DIRECTIONLESS_METRICS,
    HAZARD_LAYER_METRICS,
    METRIC_UNITS,
    NEGATIVE_METRICS,
    WARD_RESOLUTION_METRICS,
    AreaMetrics,
    MetricKey,
    RawMetrics,
)


def test_there_are_exactly_23_metrics() -> None:
    """15개 중 14개(음식점 다양성 제거, metrics.py 참조), +4는 disaster_risk
    레이어별 진단용 지표, +2는 다이얼 미반영 진단용(daily_ridership·
    residential_zone_ratio), +3은 다이얼에 반영되는 추가 지표
    (large_retail·elementary_school·middle_school)."""
    assert len(MetricKey) == 23


def test_negative_metrics_are_the_seven_penalty_axes() -> None:
    assert NEGATIVE_METRICS == frozenset(
        {
            MetricKey.PRICE_LEVEL,
            MetricKey.DISASTER_RISK,
            MetricKey.NUISANCE_VENUE,
            *HAZARD_LAYER_METRICS,
        }
    )


def test_hazard_layer_metrics_are_excluded_from_dial_scoring() -> None:
    """넣으면 같은 위험이 재해위험과 비용·위험 다이얼에 중복 반영돼 점수가 부풀어 오른다."""
    from chika.domain.service.dials import DIAL_TO_METRICS

    all_dial_metrics = {m for metrics in DIAL_TO_METRICS.values() for m in metrics}
    assert all_dial_metrics.isdisjoint(HAZARD_LAYER_METRICS)


def test_daily_ridership_has_no_direction() -> None:
    """유동인구·주거전용지역 비율이 많은/높은 게 좋은지는 사용자 취향에
    갈린다 — NEGATIVE_METRICS 에 넣는 것도 임의로 방향을 정하는 것과 같다."""
    assert DIRECTIONLESS_METRICS == frozenset(
        {MetricKey.DAILY_RIDERSHIP, MetricKey.RESIDENTIAL_ZONE_RATIO}
    )
    assert MetricKey.DAILY_RIDERSHIP not in NEGATIVE_METRICS
    assert MetricKey.RESIDENTIAL_ZONE_RATIO not in NEGATIVE_METRICS


def test_daily_ridership_is_excluded_from_dial_scoring() -> None:
    from chika.domain.service.dials import DIAL_TO_METRICS

    all_dial_metrics = {m for metrics in DIAL_TO_METRICS.values() for m in metrics}
    assert MetricKey.DAILY_RIDERSHIP not in all_dial_metrics


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
