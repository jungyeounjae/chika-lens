"""가구 형태 → 다이얼 기본값. 실사용 실패("신혼부부")에서 나온 정책이다."""

from __future__ import annotations

from chika.domain.model.criteria import Household
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import expand_dials
from chika.domain.service.personas import HOUSEHOLD_DIALS, seed_dials


def test_a_household_alone_turns_some_dials_on() -> None:
    """가구 형태만 말한 사용자도 랭킹을 받아야 한다.

    이전에는 `household` 가 월세 배수에만 쓰였고 실데이터에서 월세가 비어 있어
    couple 로 설정해도 점수가 전혀 움직이지 않았다.
    """
    seeded = seed_dials(Household.COUPLE, dict.fromkeys(Dial, 0.0))
    assert seeded[Dial.FAMILY] > 0
    assert seeded[Dial.DAILY_CONVENIENCE] > 0
    assert seeded[Dial.COST_RISK] > 0


def test_what_the_user_said_outranks_the_household_default() -> None:
    """"아이 학교가 중요해요" 로 켠 5 를 "저희는 부부예요" 가 2 로 내리면 안 된다."""
    spoken = {Dial.FAMILY: 5.0}
    assert seed_dials(Household.COUPLE, spoken)[Dial.FAMILY] == 5.0


def test_a_silent_axis_takes_the_default_rather_than_zero() -> None:
    """조건 없는 0 은 "안 본다" 는 뜻이고, 가구 형태를 말한 사용자의 뜻이 아니다."""
    spoken = {Dial.KOREAN_LIFE: 5.0}
    seeded = seed_dials(Household.FAMILY, spoken)
    assert seeded[Dial.KOREAN_LIFE] == 5.0
    assert seeded[Dial.FAMILY] == HOUSEHOLD_DIALS[Household.FAMILY][Dial.FAMILY]


def test_a_single_household_does_not_look_at_the_family_axis() -> None:
    """보육·교육과 아이 동반 시설은 1인 가구에서 가중치 0 이어야 한다."""
    seeded = seed_dials(Household.SINGLE, dict.fromkeys(Dial, 0.0))
    assert seeded[Dial.FAMILY] == 0.0


def test_the_family_axis_separates_couple_from_family() -> None:
    """둘이 같으면 가구 형태를 물어볼 이유가 없다."""
    couple = HOUSEHOLD_DIALS[Household.COUPLE][Dial.FAMILY]
    family = HOUSEHOLD_DIALS[Household.FAMILY][Dial.FAMILY]
    assert 0 < couple < family


def test_korean_life_is_never_implied_by_a_household() -> None:
    """한국 생활 중시는 가구 형태와 무관하다. 사용자가 말했을 때만 켜진다."""
    for household in Household:
        assert Dial.KOREAN_LIFE not in HOUSEHOLD_DIALS[household]


def test_the_seeded_dials_still_expand_to_valid_weights() -> None:
    """다이얼 전개는 합이 0 이면 던진다. 어느 가구 형태든 그럴 수 없다."""
    for household in Household:
        seeded = seed_dials(household, dict.fromkeys(Dial, 0.0))
        weights = expand_dials(DialSettings(seeded))
        assert sum(value for _, value in weights.items()) == 1.0
