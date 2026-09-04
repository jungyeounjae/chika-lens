"""가중치 값 객체. 합은 항상 1.0으로 정규화된다."""

from __future__ import annotations

from collections.abc import ItemsView, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from chika.domain.model.metrics import MetricKey


class Dial(StrEnum):
    """사용자 관점 다이얼 5개. LLM이 정하는 것은 이 5개의 상대 강도뿐이다 (스펙 §6.4)."""

    KOREAN_LIFE = "korean_life"
    DAILY_CONVENIENCE = "daily_convenience"
    QUALITY_OF_LIFE = "quality_of_life"
    FAMILY = "family"
    COST_RISK = "cost_risk"


@dataclass(frozen=True)
class DialSettings:
    values: Mapping[Dial, float]

    def __post_init__(self) -> None:
        for dial, strength in self.values.items():
            if not isinstance(dial, Dial):
                raise ValueError(f"unknown dial: {dial!r}")
            if strength < 0:
                raise ValueError(f"negative dial strength for {dial.value}: {strength}")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def strength(self, dial: Dial) -> float:
        return self.values.get(dial, 0.0)

    @classmethod
    def balanced(cls) -> DialSettings:
        return cls({dial: 1.0 for dial in Dial})


@dataclass(frozen=True)
class Weights:
    """지표 15개에 대한 가중치. 명시되지 않은 지표는 0."""

    values: Mapping[MetricKey, float]

    def __getitem__(self, key: MetricKey) -> float:
        return self.values.get(key, 0.0)

    def items(self) -> ItemsView[MetricKey, float]:
        return self.values.items()

    @classmethod
    def normalized(cls, raw: Mapping[MetricKey, float]) -> Weights:
        for key, value in raw.items():
            if not isinstance(key, MetricKey):
                raise ValueError(f"unknown metric: {key!r}")
            if value < 0:
                raise ValueError(f"negative weight for {key.value}: {value}")
        total = sum(raw.values())
        if total == 0:
            raise ValueError("weights sum to zero")
        return cls(MappingProxyType({key: value / total for key, value in raw.items()}))
