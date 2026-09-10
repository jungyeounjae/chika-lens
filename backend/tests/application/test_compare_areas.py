import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import DialSettings
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


def _station(station_id: str) -> Station:
    return Station(
        id=station_id, name_ja=station_id,
        ward="中野区", lat=35.70, lon=139.66, lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _usecase(stations: list[Station], raws: list[RawMetrics]) -> CompareAreas:
    return CompareAreas(areas=FakeAreaMetricsRepository(stations, raws))


def test_only_differing_axes_are_returned_first() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [
            _raw("a", cafe=99.0, supermarket=5.0),
            _raw("b", cafe=1.0, supermarket=5.0),
        ],
    )
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()), top_n=1)
    assert result.differences[0].key is MetricKey.CAFE


def test_identical_areas_have_zero_spread() -> None:
    usecase = _usecase([_station("a"), _station("b")], [_raw("a"), _raw("b")])
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()))
    assert all(diff.spread == pytest.approx(0.0) for diff in result.differences)


def test_percentiles_are_reported_per_station() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", cafe=99.0), _raw("b", cafe=1.0)],
    )
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()), top_n=1)
    diff = result.differences[0]
    assert set(diff.percentiles) == {"a", "b"}
    assert diff.percentiles["a"] > diff.percentiles["b"]


def test_totals_are_returned_for_every_station() -> None:
    usecase = _usecase(
        [_station("a"), _station("b"), _station("c")],
        [_raw("a", cafe=99.0), _raw("b", cafe=50.0), _raw("c", cafe=1.0)],
    )
    result = usecase.execute(["a", "c"], SearchCriteria(dials=DialSettings.balanced()))
    assert set(result.totals) == {"a", "c"}


def test_focus_metric_makes_the_total_track_that_metric_alone() -> None:
    """rank_areas·explain_area 와 같은 이유 — focus_metric 이 있으면
    다이얼이 전부 0이라 균등 다이얼로 대체되던 걸 막는다."""
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", cafe=99.0), _raw("b", cafe=1.0)],
    )
    criteria = SearchCriteria(dials=DialSettings({}), focus_metric=MetricKey.CAFE)
    result = usecase.execute(["a", "b"], criteria)
    assert result.totals["a"] > result.totals["b"]


def test_comparing_fewer_than_two_stations_is_rejected() -> None:
    usecase = _usecase([_station("a")], [_raw("a")])
    with pytest.raises(ValueError, match="at least two"):
        usecase.execute(["a"], SearchCriteria(dials=DialSettings.balanced()))


def test_unknown_station_raises() -> None:
    usecase = _usecase([_station("a"), _station("b")], [_raw("a"), _raw("b")])
    with pytest.raises(KeyError, match="zzz"):
        usecase.execute(["a", "zzz"], SearchCriteria(dials=DialSettings.balanced()))
