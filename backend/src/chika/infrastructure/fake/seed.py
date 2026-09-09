"""결정적 시드 데이터. 실제 데이터가 오기 전까지 전 계층을 굴리기 위한 것."""

from __future__ import annotations

import random

from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station

SEED_WARDS: tuple[str, ...] = (
    "新宿区",
    "渋谷区",
    "中野区",
    "杉並区",
    "豊島区",
    "板橋区",
    "北区",
    "足立区",
)

#: 지표별 (최소, 최대) 원시값 범위. 스케일이 제각각인 상황을 일부러 재현한다.
_METRIC_RANGE: dict[MetricKey, tuple[float, float]] = {
    MetricKey.KOREAN_RESTAURANT: (0.0, 40.0),
    MetricKey.KOREAN_GROCERY: (0.0, 8.0),
    MetricKey.KOREAN_RESIDENT_RATIO: (0.002, 0.05),
    MetricKey.SUPERMARKET: (1.0, 25.0),
    MetricKey.CONVENIENCE_STORE: (3.0, 80.0),
    MetricKey.HEALTHCARE: (2.0, 60.0),
    MetricKey.CAFE: (1.0, 90.0),
    MetricKey.PARK: (0.0, 15.0),
    MetricKey.FITNESS: (0.0, 12.0),
    MetricKey.RESTAURANT_VARIETY: (5.0, 70.0),
    MetricKey.CHILDCARE_EDUCATION: (1.0, 30.0),
    MetricKey.CHILD_FRIENDLY_VENUE: (0.0, 12.0),
    MetricKey.PRICE_LEVEL: (80_000.0, 260_000.0),
    MetricKey.DISASTER_RISK: (0.0, 1.0),
    MetricKey.NUISANCE_VENUE: (0.0, 20.0),
    MetricKey.LIQUEFACTION_RISK: (0.0, 1.0),
    MetricKey.FLOOD_RISK: (0.0, 1.0),
    MetricKey.STORM_SURGE_RISK: (0.0, 1.0),
    MetricKey.SEDIMENT_RISK: (0.0, 1.0),
    MetricKey.DAILY_RIDERSHIP: (500.0, 300_000.0),
    MetricKey.LARGE_RETAIL: (0.0, 5.0),
}

#: 결측을 일부러 섞는다. 결측 플래그 경로가 시드에서도 살아 있어야 한다.
_MISSING_PROBABILITY = 0.05


def build_seed(
    count: int = 40,
    seed: int = 20260903,
) -> tuple[list[Station], list[RawMetrics], dict[tuple[str, str], int], dict[str, int]]:
    """(역, 원시지표, 통근시간표, 시세표)를 결정적으로 만든다."""
    rng = random.Random(seed)

    stations: list[Station] = []
    raws: list[RawMetrics] = []
    prices: dict[str, int] = {}

    for index in range(count):
        station_id = f"seed_{index:03d}"
        stations.append(
            Station(
                id=station_id,
                name_ja=f"仮駅{index:03d}",
                ward=SEED_WARDS[index % len(SEED_WARDS)],
                lat=35.65 + rng.uniform(0.0, 0.15),
                lon=139.62 + rng.uniform(0.0, 0.25),
                lines=(f"仮線{index % 5}",),
            )
        )

        values: dict[MetricKey, float | None] = {}
        for key, (low, high) in _METRIC_RANGE.items():
            if rng.random() < _MISSING_PROBABILITY:
                values[key] = None
            else:
                values[key] = round(rng.uniform(low, high), 4)
        raws.append(RawMetrics(station_id=station_id, values=values))

        price = values[MetricKey.PRICE_LEVEL]
        prices[station_id] = int(price) if price is not None else 130_000

    # 통근: 시드 역 전부에서 seed_000(=도심 대용)까지의 소요시간
    hub = stations[0].id
    commute = {(station.id, hub): 5 + (i * 3) % 55 for i, station in enumerate(stations)}

    return stations, raws, commute, prices
