import pytest

from chika.application.usecase.explain_area import ExplainArea
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository, FakePriceRepository


def _station(station_id: str) -> Station:
    return Station(
        id=station_id, name_ja=station_id, name_ko=station_id,
        ward="中野区", lat=35.70, lon=139.66, lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _usecase(
    stations: list[Station], raws: list[RawMetrics], prices: dict[str, int]
) -> ExplainArea:
    return ExplainArea(
        areas=FakeAreaMetricsRepository(stations, raws),
        prices=FakePriceRepository(prices),
    )


def test_strengths_are_the_top_positive_contributions() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", korean_restaurant=99.0, park=0.0), _raw("b", korean_restaurant=0.0, park=99.0)],
        {"a": 120_000},
    )
    criteria = SearchCriteria(
        dials=DialSettings({Dial.KOREAN_LIFE: 1.0, Dial.QUALITY_OF_LIFE: 1.0})
    )
    result = usecase.execute("a", criteria)
    assert result.strengths[0].key is MetricKey.KOREAN_RESTAURANT
    assert result.strengths[0].contribution > 0
    assert result.weaknesses[0].key is MetricKey.PARK


def test_ward_resolution_flag_is_surfaced() -> None:
    # 역이 하나뿐이면 모든 기여도가 0이라 특정 지표가 상위 3개에 든다는 보장이 없다.
    # 구 단위 지표에 실제 편차를 만들어 strengths에 올라오게 한다.
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", korean_resident_ratio=0.04), _raw("b", korean_resident_ratio=0.001)],
        {},
    )
    result = usecase.execute("a", SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 1.0})))
    ratio = next(d for d in result.strengths if d.key is MetricKey.KOREAN_RESIDENT_RATIO)
    assert ratio.is_ward_resolution is True


def test_missing_metrics_are_listed() -> None:
    usecase = _usecase([_station("a")], [_raw("a", korean_grocery=None)], {})
    result = usecase.execute("a", SearchCriteria(dials=DialSettings.balanced()))
    assert MetricKey.KOREAN_GROCERY in result.missing


def test_total_matches_the_ranking_score() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", cafe=99.0), _raw("b", cafe=1.0)],
        {},
    )
    result = usecase.execute("a", SearchCriteria(dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0})))
    assert result.total > 50.0


def test_rent_is_included_when_known() -> None:
    usecase = _usecase([_station("a")], [_raw("a")], {"a": 133_000})
    result = usecase.execute("a", SearchCriteria(dials=DialSettings.balanced()))
    assert result.rent_yen == 133_000


def test_unknown_station_raises() -> None:
    usecase = _usecase([_station("a")], [_raw("a")], {})
    with pytest.raises(KeyError, match="zzz"):
        usecase.execute("zzz", SearchCriteria(dials=DialSettings.balanced()))
