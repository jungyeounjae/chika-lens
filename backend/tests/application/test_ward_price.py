"""구 단위 시세 요약. 공시지가가 아니라 MLIT 실거래가 중앙값을 낸다."""

from __future__ import annotations

from chika.application.usecase.ward_price import WardPriceRanking
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


def _station(station_id: str, ward: str) -> Station:
    return Station(id=station_id, name_ja=station_id, ward=ward, lat=35.70, lon=139.66, lines=())


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _repo(stations: list[Station], raws: list[RawMetrics]) -> FakeAreaMetricsRepository:
    return FakeAreaMetricsRepository(stations, raws)


def test_wards_are_sorted_by_median_price_ascending() -> None:
    stations = [_station("a", "足立区"), _station("b", "港区")]
    raws = [_raw("a", price_level=400_000.0), _raw("b", price_level=1_200_000.0)]
    wards = WardPriceRanking(_repo(stations, raws)).execute()
    assert [w.ward for w in wards] == ["足立区", "港区"]


def test_a_ward_with_multiple_stations_uses_the_median() -> None:
    stations = [_station("a", "足立区"), _station("b", "足立区"), _station("c", "足立区")]
    raws = [
        _raw("a", price_level=300_000.0),
        _raw("b", price_level=500_000.0),
        _raw("c", price_level=700_000.0),
    ]
    wards = WardPriceRanking(_repo(stations, raws)).execute()
    assert wards[0].median_price == 500_000.0
    assert wards[0].station_count == 3


def test_a_station_missing_price_is_excluded_from_its_ward() -> None:
    stations = [_station("a", "足立区"), _station("b", "足立区")]
    raws = [_raw("a", price_level=400_000.0), _raw("b", price_level=None)]
    wards = WardPriceRanking(_repo(stations, raws)).execute()
    assert wards[0].station_count == 1


def test_a_ward_entirely_missing_price_is_absent_not_zero() -> None:
    """결측을 0으로 채우면 '땅값이 0엔인 구'라는 거짓말이 된다."""
    stations = [_station("a", "足立区"), _station("b", "港区")]
    raws = [_raw("a", price_level=400_000.0), _raw("b", price_level=None)]
    wards = WardPriceRanking(_repo(stations, raws)).execute()
    assert [w.ward for w in wards] == ["足立区"]


def test_representative_stations_are_closest_to_the_median() -> None:
    """최고가·최저가 역이 아니라 중앙값에 가까운 역이 '전형적인' 가격대다."""
    stations = [_station(sid, "足立区") for sid in ("cheap", "typical", "expensive")]
    raws = [
        _raw("cheap", price_level=100_000.0),
        _raw("typical", price_level=500_000.0),
        _raw("expensive", price_level=9_000_000.0),
    ]
    ward = WardPriceRanking(_repo(stations, raws)).execute()[0]
    assert ward.representative[0].station.id == "typical"


def test_representative_stations_carry_commercial_density_percentiles() -> None:
    """'저평가된 이유'를 지어내지 않고 이 값으로만 말하게 하는 근거."""
    stations = [_station("a", "足立区"), _station("b", "足立区")]
    raws = [
        _raw("a", price_level=400_000.0, supermarket=1.0, convenience_store=1.0),
        _raw("b", price_level=420_000.0, supermarket=99.0, convenience_store=99.0),
    ]
    ward = WardPriceRanking(_repo(stations, raws)).execute()[0]
    percentiles = {r.station.id: r.supermarket_percentile for r in ward.representative}
    assert percentiles["a"] < percentiles["b"]


def test_no_price_data_anywhere_returns_an_empty_list() -> None:
    stations = [_station("a", "足立区")]
    raws = [_raw("a", price_level=None)]
    assert WardPriceRanking(_repo(stations, raws)).execute() == []
