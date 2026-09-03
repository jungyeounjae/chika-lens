import pytest

from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.weights import Dial, DialSettings


def _criteria(**overrides: object) -> SearchCriteria:
    base: dict[str, object] = {"dials": DialSettings.balanced()}
    base.update(overrides)
    return SearchCriteria(**base)  # type: ignore[arg-type]


def test_defaults_are_unconstrained_single_household() -> None:
    criteria = _criteria()
    assert criteria.commute_to is None
    assert criteria.commute_max_minutes is None
    assert criteria.budget_yen is None
    assert criteria.household is Household.SINGLE
    assert criteria.exclude_wards == ()


def test_replace_changes_only_the_named_field() -> None:
    original = _criteria(budget_yen=(80_000, 150_000), commute_to="shinjuku")
    updated = original.replace(budget_yen=(80_000, 120_000))
    assert updated.budget_yen == (80_000, 120_000)
    assert updated.commute_to == "shinjuku"
    assert original.budget_yen == (80_000, 150_000)  # 원본 불변


def test_replace_can_change_dials() -> None:
    updated = _criteria().replace(dials=DialSettings({Dial.FAMILY: 3.0}))
    assert updated.dials.strength(Dial.FAMILY) == 3.0


def test_inverted_budget_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="budget range"):
        _criteria(budget_yen=(200_000, 100_000))


def test_negative_commute_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="commute limit"):
        _criteria(commute_max_minutes=-5)


def test_commute_limit_without_destination_is_rejected() -> None:
    with pytest.raises(ValueError, match="commute_to"):
        _criteria(commute_max_minutes=30)
