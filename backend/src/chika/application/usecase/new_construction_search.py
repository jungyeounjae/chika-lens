"""신축 물건 검색 — 구/가격대/재해위험/정숙도로 걸러 가격 오름차순 상위 N개.

개별 조건마다 툴을 만들지 않는다 — 이 하나의 필터 + 검색으로 "안전한 곳",
"조용한 곳", "예산 안" 같은 질문을 전부 표현한다. `max_hazard_severity`/
`min_daily_ridership`/`max_daily_ridership`는 연속값이라 LLM이 "꽤 안전한
곳"·"약간 번화한 곳" 같은 뉘앙스를 임계값으로 번역할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.new_construction import NewConstructionListing
from chika.domain.repository import NewConstructionRepository


@dataclass(frozen=True)
class NewConstructionFilter:
    ward: str | None = None
    max_price_yen: int | None = None
    min_price_yen: int | None = None
    #: 0~1, 클수록 위험. 이 값을 넘는 레이어가 하나라도 있으면 제외.
    max_hazard_severity: float | None = None
    #: 최근접 역의 일평균 승하차인원(정숙도 프록시) 범위.
    min_daily_ridership: float | None = None
    max_daily_ridership: float | None = None


class NewConstructionSearch:
    def __init__(self, repo: NewConstructionRepository) -> None:
        self._repo = repo

    def execute(
        self, filter: NewConstructionFilter, limit: int = 10
    ) -> list[NewConstructionListing]:
        matched = [
            listing for listing in self._repo.listings() if self._matches(listing, filter)
        ]
        matched.sort(key=self._sort_key)
        return matched[:limit]

    def find_by_id(self, suumo_id: str) -> NewConstructionListing | None:
        return next(
            (listing for listing in self._repo.listings() if listing.suumo_id == suumo_id),
            None,
        )

    @staticmethod
    def _sort_key(listing: NewConstructionListing) -> tuple[bool, int]:
        # 가격 미정(None)은 맨 뒤로 — 0으로 두면 "가장 싼 물건"으로 둔갑한다.
        return (listing.price_min_yen is None, listing.price_min_yen or 0)

    @staticmethod
    def _matches(listing: NewConstructionListing, filter: NewConstructionFilter) -> bool:
        if filter.ward is not None and listing.ward != filter.ward:
            return False

        if filter.max_price_yen is not None:
            if listing.price_min_yen is None or listing.price_min_yen > filter.max_price_yen:
                return False
        if filter.min_price_yen is not None:
            if listing.price_max_yen is None or listing.price_max_yen < filter.min_price_yen:
                return False

        if filter.max_hazard_severity is not None:
            if any(
                level.severity > filter.max_hazard_severity
                for level in listing.hazard_summary.values()
            ):
                return False

        if filter.min_daily_ridership is not None:
            ridership = listing.quietness.daily_ridership if listing.quietness else None
            if ridership is None or ridership < filter.min_daily_ridership:
                return False
        if filter.max_daily_ridership is not None:
            ridership = listing.quietness.daily_ridership if listing.quietness else None
            if ridership is not None and ridership > filter.max_daily_ridership:
                return False

        return True
