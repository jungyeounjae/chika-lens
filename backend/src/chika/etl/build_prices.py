"""지표 13(시세) 인덱스 배치 — MLIT 부동산 거래가격 정보 (XPT001).

호출 과금이 없다 (z=13 기준 57타일 = 57콜). 최근 4분기의 중고 맨션 거래에서
역세권 반경 800m 의 ㎡당 단가 중앙값을 낸다.

**최신 분기는 공표 지연이 있다.** 2026-09-08 실측에서 2026 Q1 까지 왔고
Q2 는 0건이었다. 그래서 `--to` 를 생략하면 오늘로부터 두 분기 전을 끝으로
잡는다. 실제로 어느 분기가 왔는지는 실행 결과에 찍는다 — 창을 손으로 적으면
배치가 조용히 옛 데이터를 계속 보게 된다.

받은 원본은 `data/.cache/` 에만 두고 커밋하지 않는다 (스펙 §3.1.2).

사용법:

    export MLIT_API_KEY=...
    uv run python -m chika.etl.build_prices
    uv run python -m chika.etl.build_prices --refresh
    uv run python -m chika.etl.build_prices --to 20261 --quarters 8
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import STATION_RADIUS_METERS, Station
from chika.etl.mlit_client import MlitApiError, MlitClient, tiles_covering
from chika.etl.mlit_datasets import TRANSACTION_PRICE
from chika.etl.mlit_prices import (
    MIN_SAMPLES,
    Transaction,
    median_unit_price_near,
    parse_all,
    quarter_range,
)

#: 중앙값을 낼 창의 길이. 실측에서 4분기가 역당 중앙 134건을 주었다 — 중앙값에
#: 충분하고, 더 늘리면 표본이 늘어나는 대신 시세가 낡는다.
DEFAULT_QUARTERS = 4

#: 최신 분기의 공표 지연. 오늘이 속한 분기와 직전 분기는 아직 채워지지 않는다.
PUBLICATION_LAG_QUARTERS = 2


@dataclass(frozen=True)
class RawPrices:
    """받아온 원본과 그것을 받은 분기 창.

    창을 함께 들고 다닌다 — 창이 다른 캐시를 재사용하면 조용히 다른 지표가 된다.
    """

    window: tuple[str, str]
    features: list[dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/mlit_prices.json"))
    parser.add_argument(
        "--cache", type=Path, default=Path("data/.cache/mlit_prices_raw.json")
    )
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 재수집")
    parser.add_argument("--to", help='창의 마지막 분기 (예: "20261"). 생략하면 오늘 기준')
    parser.add_argument("--quarters", type=int, default=DEFAULT_QUARTERS)
    args = parser.parse_args()

    stations = _load_stations(args.stations)
    window = _window(args.to, args.quarters)
    print(f"분기 창: {window[0]} ~ {window[1]} ({args.quarters}분기)")

    raw = None if args.refresh else _load_cache(args.cache, window)
    if raw is None:
        raw = _fetch(stations, args.cache, window)
    else:
        print(f"캐시 사용: {args.cache}")

    transactions = parse_all(raw.features)
    _report(raw.features, transactions)

    if not transactions:
        sys.exit("중고 맨션 거래가 0건이다. 종별 필터나 분기 창이 어긋났을 수 있다.")

    index: dict[str, dict[str, float]] = {}
    missing: list[str] = []
    for station in stations:
        median = median_unit_price_near(
            station.lat, station.lon, transactions, STATION_RADIUS_METERS
        )
        if median is None:
            missing.append(station.name_ja)
            continue
        index[station.id] = {MetricKey.PRICE_LEVEL.value: round(median, 1)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _summarise(index, missing, stations, args.out)


def _window(to: str | None, quarters: int) -> tuple[str, str]:
    if to is not None:
        if len(to) != 5 or not to.isdigit():
            sys.exit(f'--to 는 "YYYYQ" 형태다 (예: 20261). 받은 값: {to!r}')
        return quarter_range(int(to[:4]), int(to[4]), quarters)

    today = dt.date.today()
    index = today.year * 4 + (today.month - 1) // 3 - PUBLICATION_LAG_QUARTERS
    year, quarter = divmod(index, 4)
    return quarter_range(year, quarter + 1, quarters)


def _load_stations(path: Path) -> list[Station]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Station(
            id=row["id"],
            name_ja=row["name_ja"],
            ward=row["ward"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            lines=tuple(row["lines"]),
        )
        for row in rows
    ]


def _fetch(
    stations: list[Station], cache: Path, window: tuple[str, str]
) -> RawPrices:
    client = MlitClient(_api_key())
    tiles = tiles_covering(
        [(s.lat, s.lon) for s in stations], TRANSACTION_PRICE.zoom
    )
    print(f"타일 {len(tiles)}개 = {len(tiles)}콜 (과금 없음)")

    params = {"from": window[0], "to": window[1]}
    collected: list[dict[str, object]] = []
    try:
        for index, (x, y) in enumerate(tiles, start=1):
            collected.extend(client.features(TRANSACTION_PRICE, x, y, params=params))
            if index % 10 == 0 or index == len(tiles):
                print(f"  {index}/{len(tiles)} 타일, 누적 {len(collected):,}건")
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"window": list(window), "features": collected}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"호출 {client.calls_made}건 사용, 원본은 {cache} 에만 둔다")
    return RawPrices(window=window, features=collected)


def _load_cache(cache: Path, window: tuple[str, str]) -> RawPrices | None:
    if not cache.exists():
        return None
    loaded = json.loads(cache.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    if loaded.get("window") != list(window):
        print(f"캐시의 분기 창이 {loaded.get('window')} 라 재수집한다")
        return None
    features = loaded.get("features")
    if not isinstance(features, list):
        return None
    return RawPrices(window=window, features=features)


def _report(
    features: list[dict[str, object]], transactions: list[Transaction]
) -> None:
    """무엇이 세어졌는지 보여준다 — 구성이 조용히 바뀌면 지표도 조용히 바뀐다."""
    def land_type(feature: dict[str, object]) -> str:
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            return "(properties 없음)"
        return str(properties.get("land_type_name_ja"))

    kinds = collections.Counter(land_type(f) for f in features)
    print(f"\n받은 거래 {len(features):,}건:")
    for kind, n in kinds.most_common():
        print(f"  {kind:<20} {n:,}")

    quarters = collections.Counter(t.quarter for t in transactions)
    print(f"\n집계 대상 {len(transactions):,}건, 분기 구성:")
    for quarter, n in sorted(quarters.items()):
        print(f"  {quarter:<18} {n:,}")


def _summarise(
    index: dict[str, dict[str, float]],
    missing: list[str],
    stations: list[Station],
    out: Path,
) -> None:
    names = {s.id: s.name_ja for s in stations}
    wards = {s.id: s.ward for s in stations}
    ranked = sorted(
        index.items(), key=lambda kv: kv[1][MetricKey.PRICE_LEVEL.value], reverse=True
    )

    def line(item: tuple[str, dict[str, float]]) -> str:
        station_id, values = item
        price = values[MetricKey.PRICE_LEVEL.value]
        return f"{names[station_id]}({wards[station_id]}) {price:,.0f}"

    print(f"\n역 {len(index)}개에 기록 -> {out}")
    print(f"  최고: {', '.join(line(i) for i in ranked[:3])}")
    print(f"  최저: {', '.join(line(i) for i in ranked[-3:])}")
    values = [v[MetricKey.PRICE_LEVEL.value] for v in index.values()]
    print(f"  중앙값: {statistics.median(values):,.0f} 엔/㎡")
    print(f"  결측 {len(missing)}개 (거래 {MIN_SAMPLES}건 미만): {', '.join(missing)}")


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
