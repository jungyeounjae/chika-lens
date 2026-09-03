"""퍼센타일 랭크 정규화 (스펙 §6.3).

z-score를 쓰지 않는다. 도쿄 상권은 롱테일이라 신주쿠·시부야 같은 극단값이
분산을 지배해 나머지 역들이 전부 평균 근처로 뭉개진다.
"""

from __future__ import annotations

from collections.abc import Sequence

from chika.domain.model.metrics import (
    NEGATIVE_METRICS,
    NEUTRAL_PERCENTILE,
    AreaMetrics,
    MetricKey,
    RawMetrics,
)


def percentile_rank(value: float, population: Sequence[float]) -> float:
    """동률을 절반으로 세는 mid-rank 퍼센타일 (0~100).

    값이 하나뿐이면 50이 되어 결측 중립값과 자연스럽게 맞물린다.
    """
    n = len(population)
    if n == 0:
        return NEUTRAL_PERCENTILE
    below = sum(1 for other in population if other < value)
    equal = sum(1 for other in population if other == value)
    return 100.0 * (below + 0.5 * equal) / n


def normalize(raws: Sequence[RawMetrics]) -> list[AreaMetrics]:
    """전체 역 집합 안에서 지표별 퍼센타일을 매긴다.

    감점 지표는 `100 - p` 로 뒤집어 이후 계층 전체를 '높을수록 좋음'으로 통일한다.
    결측은 중립값 50이지만 `missing` 에 반드시 기록된다 — 조용히 채우면 거짓말이 된다.
    """
    if not raws:
        return []

    populations: dict[MetricKey, list[float]] = {
        key: [v for raw in raws if (v := raw.get(key)) is not None] for key in MetricKey
    }

    areas: list[AreaMetrics] = []
    for raw in raws:
        percentile: dict[MetricKey, float] = {}
        missing: set[MetricKey] = set()
        for key in MetricKey:
            value = raw.get(key)
            if value is None:
                percentile[key] = NEUTRAL_PERCENTILE
                missing.add(key)
                continue
            rank = percentile_rank(value, populations[key])
            percentile[key] = 100.0 - rank if key in NEGATIVE_METRICS else rank
        areas.append(
            AreaMetrics(
                station_id=raw.station_id,
                percentile=percentile,
                missing=frozenset(missing),
            )
        )
    return areas
