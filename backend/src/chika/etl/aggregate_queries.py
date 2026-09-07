"""Places Aggregate API 쿼리 정의 — 지표와 타입 필터의 유일한 대응처.

프로브와 배치가 같은 정의를 쓰게 해서, 검증한 것과 실행하는 것이 갈라지지 않게 한다.
타입 구성의 근거는 스펙 §6.2.1(실측이 바꾼 두 지표)에 있다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.metrics import MetricKey


@dataclass(frozen=True)
class AggregateQuery:
    """computeInsights 한 번에 대응하는 조회. 호출 1건 = 이 객체 1개."""

    key: str
    included_types: tuple[str, ...]
    min_rating: float | None = None


#: 코어 지표 9개. 매달 갱신한다 (489역 × 9 = 4,401콜, 무료 한도 내).
CORE_QUERIES: Sequence[AggregateQuery] = (
    AggregateQuery(MetricKey.KOREAN_RESTAURANT, ("korean_restaurant",), 4.0),
    AggregateQuery(MetricKey.SUPERMARKET, ("supermarket",)),
    AggregateQuery(MetricKey.CONVENIENCE_STORE, ("convenience_store",)),
    AggregateQuery(MetricKey.HEALTHCARE, ("pharmacy", "hospital", "doctor")),
    AggregateQuery(MetricKey.CAFE, ("cafe",), 4.5),
    AggregateQuery(MetricKey.PARK, ("park",)),
    AggregateQuery(MetricKey.FITNESS, ("gym",), 4.5),
    AggregateQuery(
        MetricKey.CHILD_FRIENDLY_VENUE,
        ("playground", "amusement_park", "zoo", "aquarium"),
    ),
    # bar·night_club을 뺀 이유는 스펙 §6.2.1에 있다 — 그대로 두면 활기찬
    # 역세권일수록 벌점을 받는다.
    AggregateQuery(
        MetricKey.NUISANCE_VENUE,
        ("storage", "car_repair", "car_wash", "truck_stop"),
    ),
)

#: 다양성 지표(10)의 요리 바스켓. 6개월에 한 번만 갱신한다 — 한 동네의 요리
#: 구성비는 달마다 움직이지 않는다.
CUISINE_BASKET: Sequence[AggregateQuery] = tuple(
    AggregateQuery(f"cuisine:{cuisine}", (cuisine,))
    for cuisine in (
        "japanese_restaurant",
        "chinese_restaurant",
        "italian_restaurant",
        "indian_restaurant",
        "thai_restaurant",
        "fast_food_restaurant",
        "ramen_restaurant",
        "sushi_restaurant",
    )
)

#: 역 반경. 도보 10분 (스펙 §6.1).
STATION_RADIUS_M = 800
