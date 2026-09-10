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


#: 코어 지표 9개. 매달 갱신한다 (489역 × 9 = 4,401콜, 무료 한도 5,000 내).
#: 지표 11(육아·교육)은 MLIT 로 옮겼다 — `chika.etl.build_childcare` 가 담당한다.
#: 인가 시설 등록부라 학원이 섞이지 않고, 월 489콜을 돌려받았다 (스펙 §6.2.5).
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
    # 계획단지 편향 완화(스펙 §11-10) — 반경 800m 개수만 보면 소형 점포가
    # 흩어진 상권보다 대형 복합몰 하나가 있는 계획단지가 낮게 나온다.
    # supermarket 과 별도 타입이라 이중 계산이 아니다.
    AggregateQuery(MetricKey.LARGE_RETAIL, ("shopping_mall", "department_store")),
)

#: 역 반경. 도보 10분 (스펙 §6.1).
STATION_RADIUS_M = 800
