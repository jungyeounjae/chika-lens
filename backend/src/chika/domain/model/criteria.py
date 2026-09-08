"""검색 조건. IntakeAgent가 대화에서 채우는 값 객체 (스펙 §5.2).

스펙 원문의 `hard_filters: list[str]` 은 검증이 불가능해
`commute_*` / `budget_yen` / `exclude_wards` 로 구체화했다.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from chika.domain.model.weights import DialSettings


class Household(StrEnum):
    SINGLE = "single"
    COUPLE = "couple"
    FAMILY = "family"


#: 가구 형태의 사람이 읽는 이름. "신혼부부" 를 couple 로 읽었다는 사실을
#: 사용자에게 되읽어 줄 때 쓴다.
HOUSEHOLD_LABELS_KO: Mapping[Household, str] = {
    Household.SINGLE: "1인 가구",
    Household.COUPLE: "부부·2인 가구",
    Household.FAMILY: "아이가 있는 가구",
}


@dataclass(frozen=True)
class SearchCriteria:
    dials: DialSettings
    commute_to: str | None = None
    commute_max_minutes: int | None = None
    budget_yen: tuple[int, int] | None = None
    household: Household = Household.SINGLE
    exclude_wards: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.budget_yen is not None:
            low, high = self.budget_yen
            if low > high:
                raise ValueError(f"invalid budget range: {low} > {high}")
        if self.commute_max_minutes is not None:
            if self.commute_max_minutes < 0:
                raise ValueError(f"invalid commute limit: {self.commute_max_minutes}")
            if self.commute_to is None:
                raise ValueError("commute_max_minutes requires commute_to")

    def replace(self, **changes: Any) -> SearchCriteria:
        """조건 일부만 바꿔 재랭킹할 때 쓴다 (스펙 §5.5, 유스케이스 2.2-2)."""
        return dataclasses.replace(self, **changes)
