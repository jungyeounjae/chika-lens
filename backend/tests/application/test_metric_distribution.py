"""역 단위 지표 분포 (지도 색칠용). MLIT 원본 폴리곤을 대신하는 값이다."""

from __future__ import annotations

import pytest

from chika.application.usecase.metric_distribution import MetricDistribution
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


def _station(station_id: str, lat: float, lon: float, ward: str = "中野区") -> Station:
    return Station(id=station_id, name_ja=station_id, ward=ward, lat=lat, lon=lon, lines=())


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


#: 도쿄 위도에서 약 1km 간격. 반경(1500m) 안팎을 가르는 데 쓴다.
NEAR = 0.009
FAR = 0.05  # 약 5.5km — 반경 밖


def _repo(stations: list[Station], raws: list[RawMetrics]) -> FakeAreaMetricsRepository:
    return FakeAreaMetricsRepository(stations, raws)


def test_includes_the_origin_station_itself() -> None:
    stations = [_station("a", 35.70, 139.70)]
    distribution = MetricDistribution(_repo(stations, [_raw("a", park=10.0)]))
    points = distribution.execute("a", MetricKey.PARK)
    assert [p.station.id for p in points] == ["a"]


def test_a_station_within_radius_is_included() -> None:
    stations = [_station("a", 35.70, 139.70), _station("b", 35.70 + NEAR, 139.70)]
    raws = [_raw("a", park=10.0), _raw("b", park=5.0)]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.PARK)
    assert {p.station.id for p in points} == {"a", "b"}


def test_a_station_beyond_radius_is_excluded() -> None:
    stations = [_station("a", 35.70, 139.70), _station("far", 35.70 + FAR, 139.70)]
    raws = [_raw("a", park=10.0), _raw("far", park=5.0)]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.PARK)
    assert {p.station.id for p in points} == {"a"}


def test_points_carry_the_percentile_for_the_requested_metric_only() -> None:
    stations = [_station("a", 35.70, 139.70), _station("b", 35.70 + NEAR, 139.70)]
    raws = [_raw("a", park=10.0, cafe=1.0), _raw("b", park=0.0, cafe=99.0)]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.PARK)
    by_id = {p.station.id: p for p in points}
    assert by_id["a"].percentile > by_id["b"].percentile
    assert by_id["a"].raw_value == 10.0


def test_a_missing_metric_is_flagged_not_hidden() -> None:
    stations = [_station("a", 35.70, 139.70)]
    raws = [_raw("a", disaster_risk=None)]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.DISASTER_RISK)
    assert points[0].is_missing is True
    assert points[0].raw_value is None


def test_points_are_sorted_by_distance_from_the_origin() -> None:
    # 세 거리 모두 반경(1500m) 안이어야 정렬만 검증된다 — 2*NEAR(~2km)는
    # 반경 밖이라 배제 로직과 뒤섞인다.
    stations = [
        _station("far", 35.70 + NEAR * 1.3, 139.70),
        _station("a", 35.70, 139.70),
        _station("near", 35.70 + NEAR, 139.70),
    ]
    raws = [_raw(s.id) for s in stations]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.PARK)
    assert [p.station.id for p in points] == ["a", "near", "far"]


def test_unknown_station_raises() -> None:
    distribution = MetricDistribution(_repo([_station("a", 35.70, 139.70)], [_raw("a")]))
    with pytest.raises(KeyError):
        distribution.execute("ghost", MetricKey.PARK)


def test_results_are_capped_to_keep_the_map_readable() -> None:
    stations = [_station("a", 35.70, 139.70)] + [
        _station(f"s{i}", 35.70 + NEAR * 0.01 * i, 139.70) for i in range(30)
    ]
    raws = [_raw(s.id) for s in stations]
    points = MetricDistribution(_repo(stations, raws)).execute("a", MetricKey.PARK)
    assert len(points) <= 12
