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
    #: 동네 이름 부분일치(예: "光が丘"). 구보다 좁은 동네 단위 질문에 쓴다 —
    #: 주소(`address_raw`, 공식 町丁目, 예: "高松")와 최근접 역명
    #: (`quietness.station_name`) **둘 중 하나라도** 포함하면 매치한다.
    #: "히카리가오카" 같은 동네 이름은 실측 결과 공식 주소엔 안 나오고
    #: 역명으로만 나타났다(実측 2026-09-14) — 주소만 보면 놓친다. 가격순
    #: 정렬·상한 10건과 무관하게 이 조건만으로 걸러낸다.
    address_contains: str | None = None
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

    def find_by_name(self, query: str) -> list[NewConstructionListing]:
        """물건명 부분일치. `lookup_station`과 같은 패턴 — 정확히 일치하는
        것을 먼저 두고, 그다음은 이름이 짧은(더 구체적인) 순."""
        matched = [listing for listing in self._repo.listings() if query in listing.name]
        matched.sort(key=lambda listing: (listing.name != query, len(listing.name)))
        return matched

    @staticmethod
    def _sort_key(listing: NewConstructionListing) -> tuple[bool, int]:
        # 가격 미정(None)은 맨 뒤로 — 0으로 두면 "가장 싼 물건"으로 둔갑한다.
        return (listing.price_min_yen is None, listing.price_min_yen or 0)

    @staticmethod
    def _matches(listing: NewConstructionListing, filter: NewConstructionFilter) -> bool:
        if filter.ward is not None and listing.ward != filter.ward:
            return False
        if filter.address_contains is not None:
            station_name = listing.quietness.station_name if listing.quietness else ""
            if (
                filter.address_contains not in listing.address_raw
                and filter.address_contains not in station_name
            ):
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
