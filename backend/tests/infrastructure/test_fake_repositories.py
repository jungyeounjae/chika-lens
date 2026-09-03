from chika.domain.model.criteria import Household
from chika.domain.model.metrics import MetricKey
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed


def test_seed_is_deterministic() -> None:
    a_stations, a_raws, _, _ = build_seed()
    b_stations, b_raws, _, _ = build_seed()
    assert [s.id for s in a_stations] == [s.id for s in b_stations]
    assert a_raws[0].values == b_raws[0].values


def test_seed_produces_the_requested_number_of_stations() -> None:
    stations, raws, _, _ = build_seed(count=12)
    assert len(stations) == 12
    assert len(raws) == 12
    assert {s.id for s in stations} == {r.station_id for r in raws}


def test_seed_covers_every_metric() -> None:
    _, raws, _, _ = build_seed(count=5)
    for raw in raws:
        assert set(raw.values) == set(MetricKey)


def test_seed_contains_some_missing_values() -> None:
    _, raws, _, _ = build_seed(count=40)
    assert any(value is None for raw in raws for value in raw.values.values())


def test_area_repository_returns_what_it_was_given() -> None:
    stations, raws, _, _ = build_seed(count=6)
    repo = FakeAreaMetricsRepository(stations, raws)
    assert list(repo.stations()) == stations
    assert list(repo.raw_metrics()) == raws


def test_commute_repository_returns_none_for_unknown_pair() -> None:
    repo = FakeCommuteRepository({("a", "b"): 15})
    assert repo.minutes_to("a", "b") == 15
    assert repo.minutes_to("a", "zzz") is None


def test_commute_to_self_is_zero() -> None:
    repo = FakeCommuteRepository({})
    assert repo.minutes_to("a", "a") == 0


def test_price_repository_scales_with_household_size() -> None:
    repo = FakePriceRepository({"a": 100_000})
    assert repo.median_rent_yen("a", Household.SINGLE) == 100_000
    single = repo.median_rent_yen("a", Household.SINGLE)
    family = repo.median_rent_yen("a", Household.FAMILY)
    assert single is not None and family is not None and family > single
    assert repo.median_rent_yen("zzz", Household.SINGLE) is None
