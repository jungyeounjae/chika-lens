import pytest

from chika.application.usecase.explain_area import ExplainArea
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository, FakePriceRepository


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


def test_focus_metric_makes_that_metric_the_only_contributor() -> None:
    """"초등학교 몇개야?" 처럼 지표 하나만 콕 집으면, 다이얼이 전부 0이라
    균등 다이얼로 대체돼 엉뚱한 지표들이 strengths/weaknesses 에 뜨고
    focus_metric 은 안 보이던 버그의 재현 — rank_areas 와 같은 이유로
    같은 수정이 필요했다."""
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", elementary_school=8.0), _raw("b", elementary_school=0.0)],
        {},
    )
    criteria = SearchCriteria(
        dials=DialSettings({}),  # 다이얼 없음 — 전부 0
        focus_metric=MetricKey.ELEMENTARY_SCHOOL,
    )
    result = usecase.execute("a", criteria)
    assert result.strengths[0].key is MetricKey.ELEMENTARY_SCHOOL
    assert all(d.contribution == 0 for d in result.weaknesses)


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


# --- 주변 역 (지도 표시용) ---


def _at(station_id: str, lat: float, lon: float, lines: tuple[str, ...] = ()) -> Station:
    return Station(
        id=station_id, name_ja=station_id, ward="中野区",
        lat=lat, lon=lon, lines=lines,
    )


def test_nearby_stations_are_ordered_by_distance() -> None:
    stations = [
        _at("center", 35.7000, 139.7000),
        _at("far", 35.7100, 139.7000),   # 약 1.1km
        _at("near", 35.7020, 139.7000),  # 약 0.2km
    ]
    usecase = _usecase(stations, [_raw(s.id) for s in stations], {})
    result = usecase.execute("center", SearchCriteria(dials=DialSettings.balanced()))
    assert [n.station.id for n in result.nearby] == ["near", "far"]


def test_the_station_itself_is_not_listed_as_nearby() -> None:
    stations = [_at("center", 35.7000, 139.7000), _at("other", 35.7020, 139.7000)]
    usecase = _usecase(stations, [_raw(s.id) for s in stations], {})
    result = usecase.execute("center", SearchCriteria(dials=DialSettings.balanced()))
    assert "center" not in [n.station.id for n in result.nearby]


def test_stations_beyond_the_radius_are_excluded() -> None:
    """도쿄 반대편 역까지 찍으면 지도가 읽히지 않는다."""
    stations = [_at("center", 35.7000, 139.7000), _at("far", 35.8000, 139.9000)]
    usecase = _usecase(stations, [_raw(s.id) for s in stations], {})
    result = usecase.execute("center", SearchCriteria(dials=DialSettings.balanced()))
    assert result.nearby == []


def test_nearby_carries_the_distance() -> None:
    stations = [_at("center", 35.7000, 139.7000), _at("near", 35.7020, 139.7000)]
    usecase = _usecase(stations, [_raw(s.id) for s in stations], {})
    result = usecase.execute("center", SearchCriteria(dials=DialSettings.balanced()))
    assert 150 < result.nearby[0].distance_m < 300


def test_an_isolated_station_has_no_neighbours() -> None:
    """히카리가오카처럼 역이 하나뿐인 동네가 지도에서 드러나야 한다."""
    usecase = _usecase([_at("alone", 35.7000, 139.7000)], [_raw("alone")], {})
    result = usecase.execute("alone", SearchCriteria(dials=DialSettings.balanced()))
    assert result.nearby == []


def test_the_neighbour_list_is_capped() -> None:
    stations = [_at("center", 35.7000, 139.7000)] + [
        _at(f"n{i}", 35.7000 + i * 0.0005, 139.7000) for i in range(20)
    ]
    usecase = _usecase(stations, [_raw(s.id) for s in stations], {})
    result = usecase.execute("center", SearchCriteria(dials=DialSettings.balanced()))
    assert len(result.nearby) <= 8


def test_explain_carries_the_raw_count_not_only_the_percentile() -> None:
    """실사용에서 '공원은 몇개야?' 에 답하지 못했다.

    백분위 99.2 만으로는 개수를 알 수 없다. 사용자가 실제로 궁금해하는 것은
    '68개'라는 숫자다.
    """
    # 역이 하나뿐이면 기여도가 전부 0이라 공원이 상·하위 3개에 들지 못한다.
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", park=68.0), _raw("b", park=1.0)],
        {},
    )
    result = usecase.execute("a", SearchCriteria(dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0})))
    detail = next(d for d in result.strengths if d.key is MetricKey.PARK)
    assert detail.raw_value == 68.0
    assert detail.percentile > 50


def test_a_missing_metric_has_no_raw_value() -> None:
    usecase = _usecase([_station("a")], [_raw("a", park=None)], {})
    result = usecase.execute("a", SearchCriteria(dials=DialSettings.balanced()))
    details = result.strengths + result.weaknesses
    park = next((d for d in details if d.key is MetricKey.PARK), None)
    if park is not None:
        assert park.raw_value is None
