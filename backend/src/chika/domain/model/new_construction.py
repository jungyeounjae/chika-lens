"""신축 분양 물건 값 객체 — SUUMO 크롤러 + 재해/정숙도 결합 배치의 산출물을 담는다.

`etl/new_construction_hazard.py::HazardSummary`, `etl/new_construction_quietness.py::
Quietness`와 필드는 같지만 별개 타입이다 — domain은 etl을 몰라야 한다(Clean
Architecture, README "계층 규칙"). infrastructure 어댑터(FileNewConstructionRepository,
Task 2)가 JSON dict를 이 타입으로 변환한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HazardLevel:
    severity: float
    label: str


@dataclass(frozen=True)
class NewConstructionQuietness:
    station_id: str
    station_name: str
    distance_m: float
    #: 결측이면 None — 표본 부족 등으로 아직 계산 안 된 역일 수 있다. 0으로
    #: 채우지 않는다("한산한 역"과 "모르는 역"을 혼동하지 않기 위해).
    daily_ridership: float | None


@dataclass(frozen=True)
class NewConstructionListing:
    suumo_id: str
    name: str
    ward: str
    address_raw: str
    #: 지오코딩 결측이면 둘 다 None.
    lat: float | None
    lon: float | None
    price_min_yen: int | None
    price_max_yen: int | None
    floor_area_min_sqm: float | None
    floor_area_max_sqm: float | None
    delivery_period_raw: str
    url: str
    fetched_at: str
    #: 레이어별("flood"/"sediment"/"liquefaction"/"storm_surge"/"tsunami") 최고
    #: 위험도. 레이어가 없으면 그 레이어는 "데이터 없음"이지 "안전"이 아니다.
    hazard_summary: dict[str, HazardLevel]
    #: 최근접 역 매칭 실패(역 목록이 비어 있던 경우 등)면 None.
    quietness: NewConstructionQuietness | None
