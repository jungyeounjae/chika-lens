"""지표 정의. 스펙 §6.2 지표 15개 중 14개(음식점 다양성은 2026-09-10 제거)
+ 다이얼 채점에는 안 들어가는 진단용 6개(액상화·홍수·해일·토사재해 4개 +
유동인구·주거전용지역 비율 2개) + 다이얼에 반영되는 추가 지표 3개
(복합쇼핑몰·백화점, 초등학교, 중학교)의 유일한 정의처."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

NEUTRAL_PERCENTILE = 50.0


class MetricKey(StrEnum):
    """스펙 §6.2의 지표 15개 중 14개(10번 음식점 다양성은 결번). 순서는
    스펙 표의 번호와 같다.

    16~19(`LIQUEFACTION_RISK`·`FLOOD_RISK`·`STORM_SURGE_RISK`·`SEDIMENT_RISK`)는
    스펙 §6.2에 없다 — `disaster_risk`(14)는 이 4개 레이어의 **최댓값**이라
    어느 레이어가 원인인지가 합치는 순간 사라진다. "홍수만", "액상화만"처럼
    레이어 하나를 따로 물어보는 질문에 답하려고 원래 raw severity를 그대로
    남겨 둔다. `dials.DIAL_TO_METRICS`에는 일부러 안 넣는다 — 넣으면 같은
    위험이 재해위험과 비용·위험 다이얼에 여러 번 반영돼 가중치가 부풀고,
    스펙 §6.2가 정한 15개 밖에서 종합 점수가 바뀐다. `Weights[key]`는
    매핑에 없는 키를 0으로 돌려주므로(weights.py) 정규화·조회 툴
    (metric_extremes 등)은 그대로 재사용되면서 점수에는 기여하지 않는다.

    `LARGE_RETAIL`(21, 복합쇼핑몰·백화점)은 위 5개와 다르다 — 진단용이
    아니라 `dials.DIAL_TO_METRICS`의 `daily_convenience`에 정식으로
    들어간다. "光が丘처럼 슈퍼 2곳뿐이어도 대형 복합몰 하나가 그 역할을
    한다"는 계획단지 측정 편향(스펙 §11-10)을 종합 점수에도 반영하려는
    것이라, 진단만 하고 점수엔 안 넣는 나머지 5개와 존재 이유가 다르다.

    `ELEMENTARY_SCHOOL`·`MIDDLE_SCHOOL`(22·23)은 원래 `CHILDCARE_EDUCATION`
    (11) 하나에 합쳐져 있던 MLIT XKT006(学校) 학교 종별을 쪼갠 것이다 —
    "초등학교 몇 개?"에 답하려면 유치원·보육시설과 초등·중학교가 같은
    숫자에 섞여 있으면 안 된다. `CHILDCARE_EDUCATION`은 이제 유치원·
    보육시설(XKT007)만 센다. 셋 다 `family` 다이얼에 들어간다 —
    `LARGE_RETAIL`과 같은 이유로, 진단용이 아니라 실제 종합 점수에
    반영해야 하는 값이다.

    `RESIDENTIAL_ZONE_RATIO`(24)는 "조용함"을 직접 재는 지표가 없어서
    만든 대리 지표다 — MLIT XKT002(用途地域)에서 법적으로 상가·공장이
    금지된 住居専用地域(1~4번)이 역 반경 800m 안에서 차지하는 면적
    비율이다. `DAILY_RIDERSHIP`과 같은 이유로 진단용이고 다이얼에
    안 들어간다 — 조용한 게 좋은지 번화가가 좋은지는 사용자 취향이다.
    """

    KOREAN_RESTAURANT = "korean_restaurant"          # 1
    KOREAN_GROCERY = "korean_grocery"                # 2
    KOREAN_RESIDENT_RATIO = "korean_resident_ratio"  # 3
    SUPERMARKET = "supermarket"                      # 4
    CONVENIENCE_STORE = "convenience_store"          # 5
    HEALTHCARE = "healthcare"                        # 6
    CAFE = "cafe"                                    # 7
    PARK = "park"                                    # 8
    FITNESS = "fitness"                              # 9
    # 10(음식점 다양성)은 결번이다 — 2026-09-10 제거. Aggregate 8종 콜
    # 배치를 끝내 한 번도 안 돌려 489역 전부가 영원히 결측이었고, 그
    # 결측 표시 자체가 매 답변에 잡음을 더했다. 나머지 번호는 스펙
    # §6.2 원문 번호와 맞추려고 당기지 않는다.
    CHILDCARE_EDUCATION = "childcare_education"      # 11
    CHILD_FRIENDLY_VENUE = "child_friendly_venue"    # 12
    PRICE_LEVEL = "price_level"                      # 13 (감점)
    DISASTER_RISK = "disaster_risk"                  # 14 (감점)
    NUISANCE_VENUE = "nuisance_venue"                # 15 (감점)
    LIQUEFACTION_RISK = "liquefaction_risk"          # 16 (감점, 다이얼 미반영·진단용)
    FLOOD_RISK = "flood_risk"                        # 17 (감점, 다이얼 미반영·진단용)
    STORM_SURGE_RISK = "storm_surge_risk"            # 18 (감점, 다이얼 미반영·진단용)
    SEDIMENT_RISK = "sediment_risk"                  # 19 (감점, 다이얼 미반영·진단용)
    DAILY_RIDERSHIP = "daily_ridership"              # 20 (방향 없음, 다이얼 미반영·진단용)
    LARGE_RETAIL = "large_retail"                     # 21 (다이얼 반영 — daily_convenience)
    ELEMENTARY_SCHOOL = "elementary_school"           # 22 (다이얼 반영 — family)
    MIDDLE_SCHOOL = "middle_school"                   # 23 (다이얼 반영 — family)
    RESIDENTIAL_ZONE_RATIO = "residential_zone_ratio" # 24 (방향 없음, 다이얼 미반영·진단용)


#: disaster_risk 를 구성하는 4개 레이어별 진단용 지표. 순회할 때 한 곳만
#: 고치면 되게 묶어 둔다 (build_hazards.py, seed.py 가 이 목록을 쓴다).
HAZARD_LAYER_METRICS: tuple[MetricKey, ...] = (
    MetricKey.LIQUEFACTION_RISK,
    MetricKey.FLOOD_RISK,
    MetricKey.STORM_SURGE_RISK,
    MetricKey.SEDIMENT_RISK,
)

#: "높을수록 좋다/나쁘다"가 없는 지표. `AreaMetrics.percentile`의 문서화된
#: 불변식("전 지표가 높을수록 좋음")의 예외다 — 유동인구가 많은 게
#: 좋은지 적은 게 좋은지는 사용자 취향(번화가 vs 정숙한 동네)에 갈려서
#: 방향을 미리 정할 수 없다. `NEGATIVE_METRICS`에도 안 넣는다 — 넣으면
#: "적을수록 좋다"고 임의로 정하는 것과 같다. 그래서 이 지표의 percentile
#: 은 "높을수록 좋다"가 아니라 **"높을수록 승하차가 많다"**는 뜻일 뿐이다.
#: `RESIDENTIAL_ZONE_RATIO`도 같은 이유로 여기 있다 — 주거전용지역
#: 비율이 높은 게 좋은지(조용함을 원하는 사람) 낮은 게 좋은지(번화가를
#: 원하는 사람)는 취향이지 사실이 아니다.
DIRECTIONLESS_METRICS: frozenset[MetricKey] = frozenset(
    {MetricKey.DAILY_RIDERSHIP, MetricKey.RESIDENTIAL_ZONE_RATIO}
)

#: 원시값이 높을수록 나쁜 지표. 정규화 단계에서 퍼센타일을 뒤집는다.
NEGATIVE_METRICS: frozenset[MetricKey] = frozenset(
    {
        MetricKey.PRICE_LEVEL,
        MetricKey.DISASTER_RISK,
        MetricKey.NUISANCE_VENUE,
        *HAZARD_LAYER_METRICS,
    }
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
    # 유치원·보육시설만(XKT007). 초등·중학교는 22·23으로 분리했다.
    MetricKey.CHILDCARE_EDUCATION: "보육시설",
    MetricKey.CHILD_FRIENDLY_VENUE: "아이 동반 시설",
    MetricKey.PRICE_LEVEL: "시세",
    MetricKey.DISASTER_RISK: "재해위험",
    MetricKey.NUISANCE_VENUE: "감점 상권",
    MetricKey.LIQUEFACTION_RISK: "액상화위험",
    MetricKey.FLOOD_RISK: "홍수위험",
    MetricKey.STORM_SURGE_RISK: "해일위험",
    MetricKey.SEDIMENT_RISK: "토사재해위험",
    MetricKey.DAILY_RIDERSHIP: "유동인구",
    MetricKey.LARGE_RETAIL: "복합쇼핑몰·백화점",
    MetricKey.ELEMENTARY_SCHOOL: "초등학교",
    MetricKey.MIDDLE_SCHOOL: "중학교",
    MetricKey.RESIDENTIAL_ZONE_RATIO: "주거전용지역 비율",
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
    MetricKey.CHILDCARE_EDUCATION: "곳",
    MetricKey.CHILD_FRIENDLY_VENUE: "곳",
    # 매매 ㎡당 단가. 월세가 아니다 (MLIT 거래가격에는 임대가 없다).
    MetricKey.PRICE_LEVEL: "엔/㎡",
    # 액상화·홍수·해일·토사 4개 레이어를 정규화해 합친 심각도. 사건 확률이
    # 아니라서 "%"로 부르면 "42% 확률로 침수"처럼 잘못 읽힌다(mlit_hazards.py).
    MetricKey.DISASTER_RISK: "지수(0~1, 클수록 위험)",
    MetricKey.NUISANCE_VENUE: "곳",
    # disaster_risk 와 같은 0~1 심각도 척도, 4개 레이어 중 하나만 뗀 값.
    MetricKey.LIQUEFACTION_RISK: "지수(0~1, 클수록 위험)",
    MetricKey.FLOOD_RISK: "지수(0~1, 클수록 위험)",
    MetricKey.STORM_SURGE_RISK: "지수(0~1, 클수록 위험)",
    MetricKey.SEDIMENT_RISK: "지수(0~1, 클수록 위험)",
    # 일평균 승하차인원. 대표 레코드 합산(mlit_ridership.py) — 개수가 아니다.
    MetricKey.DAILY_RIDERSHIP: "명/일",
    MetricKey.LARGE_RETAIL: "곳",
    MetricKey.ELEMENTARY_SCHOOL: "곳",
    MetricKey.MIDDLE_SCHOOL: "곳",
    MetricKey.RESIDENTIAL_ZONE_RATIO: "%",
}


#: 원시값이 0~1 분수로 저장된 지표. 표시할 때는 %로 옮긴다.
#:
#: `korean_resident_ratio` 는 `한국 국적자 / 구 인구` 라 0.025811 처럼 들어온다.
#: 단위만 "%"로 붙였더니 실사용에서 "한국 국적 비율 0.025811%" 가 나갔다 —
#: 실제 2.58% 를 100배 작게 말한 것이다. 백분위는 단조 변환에 영향받지 않아
#: 랭킹은 옳았고 서술만 틀렸다. 그래서 인덱스를 다시 굽지 않고 표시에서 옮긴다.
RATIO_METRICS: frozenset[MetricKey] = frozenset(
    {MetricKey.KOREAN_RESIDENT_RATIO, MetricKey.RESIDENTIAL_ZONE_RATIO}
)


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
    """정규화된 퍼센타일(0~100). `DIRECTIONLESS_METRICS`를 뺀 전 지표가
    '높을수록 좋음'으로 통일되어 있다."""

    station_id: str
    percentile: Mapping[MetricKey, float]
    missing: frozenset[MetricKey]

    def __post_init__(self) -> None:
        absent = [key for key in MetricKey if key not in self.percentile]
        if absent:
            raise ValueError(f"missing percentile for: {[k.value for k in absent]}")
