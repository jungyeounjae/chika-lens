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


def test_commute_repository_returns_every_origin_for_one_destination() -> None:
    repo = FakeCommuteRepository({("a", "hub"): 15, ("b", "hub"): 40, ("a", "other"): 5})
    assert repo.minutes_from_all("hub") == {"a": 15, "b": 40, "hub": 0}


def test_commute_omits_origins_it_does_not_know() -> None:
    """키의 부재가 '알 수 없음'이다. 호출자는 이를 탈락이 아니라 판단 보류로 다룬다."""
    repo = FakeCommuteRepository({("a", "hub"): 15})
    assert "zzz" not in repo.minutes_from_all("hub")


def test_commute_to_self_is_zero() -> None:
    assert FakeCommuteRepository({}).minutes_from_all("a") == {"a": 0}


def test_price_repository_scales_with_household_size() -> None:
    repo = FakePriceRepository({"a": 100_000})
    single = repo.median_rents(Household.SINGLE)
    family = repo.median_rents(Household.FAMILY)
    assert single["a"] == 100_000
    assert family["a"] > single["a"]


def test_price_repository_omits_stations_it_does_not_know() -> None:
    assert "zzz" not in FakePriceRepository({"a": 100_000}).median_rents(Household.SINGLE)
