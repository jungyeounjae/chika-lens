"""점수와 지표별 기여도. 기여도가 있어야 LLM이 이유를 지어내지 않는다."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chika.domain.model.metrics import MetricKey


@dataclass(frozen=True)
class AreaScore:
    station_id: str
    total: float
    contributions: Mapping[MetricKey, float]
    missing: frozenset[MetricKey]

    def _sorted(self) -> list[tuple[MetricKey, float]]:
        return sorted(
            self.contributions.items(),
            key=lambda item: (-item[1], item[0].value),
        )

    def top_drivers(self, n: int = 3) -> list[tuple[MetricKey, float]]:
        return self._sorted()[:n]

    def bottom_drivers(self, n: int = 3) -> list[tuple[MetricKey, float]]:
        return list(reversed(self._sorted()))[:n]
