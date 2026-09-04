"""역세권 랭킹 유스케이스 (스펙 §2.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey
from chika.domain.model.score import AreaScore
from chika.domain.model.station import Station
from chika.domain.repository import (
    AreaMetricsRepository,
    CommuteRepository,
    PriceRepository,
)
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import rank


@dataclass(frozen=True)
class RankedArea:
    station: Station
    score: AreaScore
    rent_yen: int | None
    commute_minutes: int | None
    percentile: Mapping[MetricKey, float]


class RankAreas:
    def __init__(
        self,
        areas: AreaMetricsRepository,
        commute: CommuteRepository,
        prices: PriceRepository,
    ) -> None:
        self._areas = areas
        self._commute = commute
        self._prices = prices

    def known_stations(self) -> list[Station]:
        """알려진 역 목록. interface 계층이 통근지 이름을 역 id로 해석할 때 쓴다."""
        return list(self._areas.stations())

    def execute(self, criteria: SearchCriteria, limit: int = 5) -> list[RankedArea]:
        stations = {station.id: station for station in self._areas.stations()}
        # 퍼센타일은 필터 이전, 전체 모집단 기준으로 계산한다 (스펙 §6.3).
        normalized = normalize(self._areas.raw_metrics())
        percentiles_by_id = {area.station_id: area.percentile for area in normalized}
        scores = rank(normalized, expand_dials(criteria.dials))

        results: list[RankedArea] = []
        for area_score in scores:
            station = stations.get(area_score.station_id)
            if station is None:
                continue
            if station.ward in criteria.exclude_wards:
                continue

            rent = self._prices.median_rent_yen(station.id, criteria.household)
            if not _within_budget(rent, criteria):
                continue

            minutes = (
                self._commute.minutes_to(station.id, criteria.commute_to)
                if criteria.commute_to is not None
                else None
            )
            if not _within_commute(minutes, criteria):
                continue

            results.append(
                RankedArea(
                    station=station,
                    score=area_score,
                    rent_yen=rent,
                    commute_minutes=minutes,
                    percentile=percentiles_by_id[area_score.station_id],
                )
            )
            if len(results) >= limit:
                break
        return results


def _within_budget(rent: int | None, criteria: SearchCriteria) -> bool:
    """시세를 모르면 통과시킨다 — 데이터 부재를 탈락으로 바꾸지 않는다."""
    if criteria.budget_yen is None or rent is None:
        return True
    low, high = criteria.budget_yen
    return low <= rent <= high


def _within_commute(minutes: int | None, criteria: SearchCriteria) -> bool:
    """통근 시간을 모르면 통과시키고 화면에서 '확인 필요'로 표기하게 한다."""
    if criteria.commute_max_minutes is None or minutes is None:
        return True
    return minutes <= criteria.commute_max_minutes
