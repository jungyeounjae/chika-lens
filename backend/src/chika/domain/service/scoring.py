"""점수 계산 (스펙 §6.4). 외부 의존 0, 순수 함수.

LLM은 여기 있는 어떤 수치도 계산하지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

from chika.domain.model.metrics import NEUTRAL_PERCENTILE, AreaMetrics, MetricKey
from chika.domain.model.score import AreaScore
from chika.domain.model.weights import Weights


def score(area: AreaMetrics, weights: Weights) -> AreaScore:
    contributions = {
        key: weights[key] * (area.percentile[key] - NEUTRAL_PERCENTILE) for key in MetricKey
    }
    return AreaScore(
        station_id=area.station_id,
        total=NEUTRAL_PERCENTILE + sum(contributions.values()),
        contributions=contributions,
        missing=area.missing,
    )


def rank(areas: Sequence[AreaMetrics], weights: Weights) -> list[AreaScore]:
    """총점 내림차순. 동점은 station_id 오름차순으로 깨서 결과를 결정적으로 만든다."""
    scores = [score(area, weights) for area in areas]
    return sorted(scores, key=lambda s: (-s.total, s.station_id))
