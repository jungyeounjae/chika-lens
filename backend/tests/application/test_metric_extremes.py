"""489역 전체 기준 지표 극값. 정렬 자체를 코드가 한다 — LLM이 방향을
다시 계산하다 뒤집는 사고를 아예 없애기 위해서다."""

from __future__ import annotations

from chika.application.usecase.metric_extremes import MetricExtremes
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


def _station(station_id: str, ward: str = "中野区") -> Station:
    return Station(id=station_id, name_ja=station_id, ward=ward, lat=35.70, lon=139.66, lines=())


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _repo(stations: list[Station], raws: list[RawMetrics]) -> FakeAreaMetricsRepository:
    return FakeAreaMetricsRepository(stations, raws)


def test_worst_first_orders_by_percentile_ascending() -> None:
    """disaster_risk 는 감점 지표라 raw 가 클수록 위험, percentile 은 반대로
    뒤집혀 있다 — worst_first 는 그 percentile 오름차순이어야 한다."""
    stations = [_station("safe"), _station("risky")]
    raws = [_raw("safe", disaster_risk=0.1), _raw("risky", disaster_risk=1.0)]
    points = MetricExtremes(_repo(stations, raws)).execute(
        MetricKey.DISASTER_RISK, worst_first=True, limit=2
    )
    assert [p.station.id for p in points] == ["risky", "safe"]


def test_best_first_reverses_the_order() -> None:
    stations = [_station("safe"), _station("risky")]
    raws = [_raw("safe", disaster_risk=0.1), _raw("risky", disaster_risk=1.0)]
    points = MetricExtremes(_repo(stations, raws)).execute(
        MetricKey.DISASTER_RISK, worst_first=False, limit=2
    )
    assert [p.station.id for p in points] == ["safe", "risky"]


def test_a_missing_station_never_appears_in_the_extremes() -> None:
    """결측(중립값 50.0)이 섞이면 '데이터 없는 역'이 '중간 위험 역'으로
    둔갑한다 — 아예 후보에서 뺀다."""
    stations = [_station("a"), _station("missing")]
    raws = [_raw("a", disaster_risk=1.0), _raw("missing", disaster_risk=None)]
    points = MetricExtremes(_repo(stations, raws)).execute(
        MetricKey.DISASTER_RISK, worst_first=True, limit=10
    )
    assert "missing" not in {p.station.id for p in points}


def test_the_result_is_capped() -> None:
    stations = [_station(f"s{i}") for i in range(20)]
    raws = [_raw(f"s{i}", disaster_risk=float(i)) for i in range(20)]
    points = MetricExtremes(_repo(stations, raws)).execute(
        MetricKey.DISASTER_RISK, worst_first=True, limit=999
    )
    assert len(points) <= 10


def test_points_carry_the_raw_value_too() -> None:
    """"몇 개야?"에 답하려면 percentile 만으로는 부족하다."""
    stations = [_station("a")]
    raws = [_raw("a", park=42.0)]
    points = MetricExtremes(_repo(stations, raws)).execute(
        MetricKey.PARK, worst_first=True, limit=1
    )
    assert points[0].raw_value == 42.0
