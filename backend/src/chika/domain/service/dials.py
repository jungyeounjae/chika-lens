"""다이얼 5개 → 지표 15개(+ large_retail) 가중치 전개 (스펙 §6.4의 고정 매핑 표)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings, Weights

DIAL_TO_METRICS: Mapping[Dial, tuple[MetricKey, ...]] = MappingProxyType(
    {
        Dial.KOREAN_LIFE: (
            MetricKey.KOREAN_RESTAURANT,
            MetricKey.KOREAN_GROCERY,
            MetricKey.KOREAN_RESIDENT_RATIO,
        ),
        Dial.DAILY_CONVENIENCE: (
            MetricKey.SUPERMARKET,
            MetricKey.CONVENIENCE_STORE,
            MetricKey.HEALTHCARE,
            # 光が丘처럼 슈퍼가 2곳뿐이어도 대형 복합몰 하나가 그 역할을
            # 하는 계획단지 편향(스펙 §11-10)을 종합 점수에도 반영한다.
            MetricKey.LARGE_RETAIL,
        ),
        Dial.QUALITY_OF_LIFE: (
            MetricKey.CAFE,
            MetricKey.PARK,
            MetricKey.FITNESS,
        ),
        Dial.FAMILY: (
            MetricKey.CHILDCARE_EDUCATION,
            MetricKey.CHILD_FRIENDLY_VENUE,
            # 원래 CHILDCARE_EDUCATION 하나에 합쳐져 있던 초등·중학교를 분리했다
            # (2026-09-10) — "초등학교 몇 개?" 질문에 답하려면 유치원과 섞이면 안 된다.
            MetricKey.ELEMENTARY_SCHOOL,
            MetricKey.MIDDLE_SCHOOL,
        ),
        Dial.COST_RISK: (
            MetricKey.PRICE_LEVEL,
            MetricKey.DISASTER_RISK,
            MetricKey.NUISANCE_VENUE,
        ),
    }
)


def expand_dials(settings: DialSettings) -> Weights:
    """다이얼 강도를 소속 지표에 균등 분배한 뒤 합이 1이 되도록 정규화한다.

    모든 다이얼이 0이면 균등 다이얼로 대체한다 — 랭킹을 못 내는 것보다 낫다.
    """
    if all(settings.strength(dial) == 0.0 for dial in Dial):
        settings = DialSettings.balanced()

    raw: dict[MetricKey, float] = {}
    for dial, metrics in DIAL_TO_METRICS.items():
        share = settings.strength(dial) / len(metrics)
        for metric in metrics:
            raw[metric] = share
    return Weights.normalized(raw)
