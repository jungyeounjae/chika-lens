"""지표 정의. 15개 지표 키의 유일한 정의처."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

NEUTRAL_PERCENTILE = 50.0


class MetricKey(StrEnum):
    """스펙 §6.2의 지표 15개. 순서는 스펙 표의 번호와 같다."""

    KOREAN_RESTAURANT = "korean_restaurant"          # 1
    KOREAN_GROCERY = "korean_grocery"                # 2
    KOREAN_RESIDENT_RATIO = "korean_resident_ratio"  # 3
    SUPERMARKET = "supermarket"                      # 4
    CONVENIENCE_STORE = "convenience_store"          # 5
    HEALTHCARE = "healthcare"                        # 6
    CAFE = "cafe"                                    # 7
    PARK = "park"                                    # 8
    FITNESS = "fitness"                              # 9
    RESTAURANT_VARIETY = "restaurant_variety"        # 10
    CHILDCARE_EDUCATION = "childcare_education"      # 11
    CHILD_FRIENDLY_VENUE = "child_friendly_venue"    # 12
    PRICE_LEVEL = "price_level"                      # 13 (감점)
    DISASTER_RISK = "disaster_risk"                  # 14 (감점)
    NUISANCE_VENUE = "nuisance_venue"                # 15 (감점)


#: 원시값이 높을수록 나쁜 지표. 정규화 단계에서 퍼센타일을 뒤집는다.
NEGATIVE_METRICS: frozenset[MetricKey] = frozenset(
    {MetricKey.PRICE_LEVEL, MetricKey.DISASTER_RISK, MetricKey.NUISANCE_VENUE}
)

#: 역세권이 아니라 구 단위 해상도인 지표. 화면에 반드시 명시해야 한다 (스펙 §3.2).
WARD_RESOLUTION_METRICS: frozenset[MetricKey] = frozenset({MetricKey.KOREAN_RESIDENT_RATIO})


@dataclass(frozen=True)
class RawMetrics:
    """정규화 이전의 원시 지표값. `None` 은 결측을 뜻한다."""

    station_id: str
    values: Mapping[MetricKey, float | None]

    def __post_init__(self) -> None:
        for key in self.values:
            if not isinstance(key, MetricKey):
                raise ValueError(f"unknown metric: {key!r}")

    def get(self, key: MetricKey) -> float | None:
        return self.values.get(key)


@dataclass(frozen=True)
class AreaMetrics:
    """정규화된 퍼센타일(0~100). 전 지표가 '높을수록 좋음'으로 통일되어 있다."""

    station_id: str
    percentile: Mapping[MetricKey, float]
    missing: frozenset[MetricKey]

    def __post_init__(self) -> None:
        absent = [key for key in MetricKey if key not in self.percentile]
        if absent:
            raise ValueError(f"missing percentile for: {[k.value for k in absent]}")

    def is_ward_resolution(self, key: MetricKey) -> bool:
        return key in WARD_RESOLUTION_METRICS
