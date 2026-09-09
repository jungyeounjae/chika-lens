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

#: 지표의 사람이 읽는 이름. 화면과 서술이 같은 말을 쓰게 하는 유일한 정의처.
#:
#: 프론트에만 두었더니 에이전트가 내부 키를 그대로 노출했다 — 실사용에서
#: "창고·정비소·세차장 수인 nuisance_venue도 반영되지 않아" 라고 답했다.
#: 화면은 "감점 상권"이라고 쓰는데 서술은 키를 쓰는, 같은 것을 두 이름으로
#: 부르는 상태였다.
#:
#: 역명은 일본어 그대로 두지만(부동산 검색·발권에 쓰는 실용 문자열) 지표
#: 이름은 설명이므로 한국어로 옮긴다.
METRIC_LABELS_KO: Mapping[MetricKey, str] = {
    MetricKey.KOREAN_RESTAURANT: "한식당",
    MetricKey.KOREAN_GROCERY: "한국 식자재점",
    MetricKey.KOREAN_RESIDENT_RATIO: "한국 국적 비율",
    MetricKey.SUPERMARKET: "슈퍼마켓",
    MetricKey.CONVENIENCE_STORE: "편의점",
    MetricKey.HEALTHCARE: "의료·약국",
    MetricKey.CAFE: "카페",
    MetricKey.PARK: "공원",
    MetricKey.FITNESS: "피트니스",
    MetricKey.RESTAURANT_VARIETY: "음식점 다양성",
    MetricKey.CHILDCARE_EDUCATION: "보육·교육",
    MetricKey.CHILD_FRIENDLY_VENUE: "아이 동반 시설",
    MetricKey.PRICE_LEVEL: "시세",
    MetricKey.DISASTER_RISK: "재해위험",
    MetricKey.NUISANCE_VENUE: "감점 상권",
}

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
    # 액상화·홍수·해일·토사 4개 레이어를 정규화해 합친 심각도. 사건 확률이
    # 아니라서 "%"로 부르면 "42% 확률로 침수"처럼 잘못 읽힌다(mlit_hazards.py).
    MetricKey.DISASTER_RISK: "지수(0~1, 클수록 위험)",
    MetricKey.NUISANCE_VENUE: "곳",
}


#: 원시값이 0~1 분수로 저장된 지표. 표시할 때는 %로 옮긴다.
#:
#: `korean_resident_ratio` 는 `한국 국적자 / 구 인구` 라 0.025811 처럼 들어온다.
#: 단위만 "%"로 붙였더니 실사용에서 "한국 국적 비율 0.025811%" 가 나갔다 —
#: 실제 2.58% 를 100배 작게 말한 것이다. 백분위는 단조 변환에 영향받지 않아
#: 랭킹은 옳았고 서술만 틀렸다. 그래서 인덱스를 다시 굽지 않고 표시에서 옮긴다.
RATIO_METRICS: frozenset[MetricKey] = frozenset({MetricKey.KOREAN_RESIDENT_RATIO})


def display_raw_value(key: MetricKey, raw: float | None) -> float | None:
    """서술·화면에 내보낼 원시값. 분수 지표만 %로 환산한다."""
    if raw is None:
        return None
    if key in RATIO_METRICS:
        return round(raw * 100, 2)
    return raw


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
