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

#: 원시값의 단위. 대부분은 반경 800m 안의 시설 개수지만 셋은 다르다.
#:
#: 단위가 없으면 LLM 이 `raw_value` 를 전부 개수로 읽는다 — 시세 1,100,000 을
#: "110만 곳", 한국 국적 비율 3.5 를 "3.5곳"으로 말한다. 지표 13 을 붙이면서
#: 드러났지만 지표 3·10 에 이미 있던 결함이다.
METRIC_UNITS: Mapping[MetricKey, str] = {
    MetricKey.KOREAN_RESTAURANT: "곳",
    MetricKey.KOREAN_GROCERY: "곳",
    MetricKey.KOREAN_RESIDENT_RATIO: "%",
    MetricKey.SUPERMARKET: "곳",
    MetricKey.CONVENIENCE_STORE: "곳",
    MetricKey.HEALTHCARE: "곳",
    MetricKey.CAFE: "곳",
    MetricKey.PARK: "곳",
    MetricKey.FITNESS: "곳",
    # 유효 종 수 exp(H). "8종 중 3.13종"처럼 읽는다 — 개수가 아니다.
    MetricKey.RESTAURANT_VARIETY: "종",
    MetricKey.CHILDCARE_EDUCATION: "곳",
    MetricKey.CHILD_FRIENDLY_VENUE: "곳",
    # 매매 ㎡당 단가. 월세가 아니다 (MLIT 거래가격에는 임대가 없다).
    MetricKey.PRICE_LEVEL: "엔/㎡",
    # 아직 수집하지 않는 지표라 쓰이지 않는다. 지표를 만들 때 함께 확정한다
    # (스펙 §11-9).
    MetricKey.DISASTER_RISK: "%",
    MetricKey.NUISANCE_VENUE: "곳",
}


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
