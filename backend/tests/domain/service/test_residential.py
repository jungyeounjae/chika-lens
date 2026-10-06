from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.service.residential import is_non_residential


def _raw(**values: float | None) -> RawMetrics:
    base: dict[MetricKey, float | None] = {
        MetricKey.RESIDENTIAL_ZONE_RATIO: 0.0,
        MetricKey.SUPERMARKET: 5.0,
        MetricKey.PRICE_LEVEL: 1_000_000.0,
    }
    for name, value in values.items():
        base[MetricKey(name)] = value
    return RawMetrics(station_id="s", values=base)


def test_no_supermarket_and_no_residential_zone_is_non_residential() -> None:
    assert is_non_residential(_raw(supermarket=0.0))


def test_missing_price_and_no_residential_zone_is_non_residential() -> None:
    assert is_non_residential(_raw(price_level=None))


def test_residential_zone_keeps_station_even_without_supermarket_or_price() -> None:
    # 舎人公園: 거래가 없어도 주거지역이면 주거지다.
    assert not is_non_residential(
        _raw(residential_zone_ratio=0.55, supermarket=0.0, price_level=None)
    )


def test_non_residential_zone_alone_is_not_enough() -> None:
    assert not is_non_residential(_raw())


def test_missing_zoning_is_not_evidence_of_non_residential() -> None:
    assert not is_non_residential(
        _raw(residential_zone_ratio=None, supermarket=0.0, price_level=None)
    )
