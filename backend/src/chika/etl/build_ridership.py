"""지표 20(유동인구) 인덱스 배치 — MLIT XKT015(駅別乗降객수).

호출 과금이 없다. z=13 타일로 역세권을 덮어 노선 구간 레코드를 받고,
대표 레코드만 그룹 코드(300m 통합역)별로 합산한 뒤(mlit_ridership.py),
그 그룹의 대표점과 가장 가까운 우리 역에 매칭한다 — S12 그룹 코드는
우리 역 마스터에 없어서 이름이 아니라 좌표로 잇는다. 매칭 반경은 MLIT
자신의 통합 기준과 같은 300m — 그보다 멀면 다른 역으로 잘못 붙일 위험이
매칭 실패보다 크다.

사용법:

    export MLIT_API_KEY=...
    uv run --extra etl python -m chika.etl.build_ridership
    uv run --extra etl python -m chika.etl.build_ridership --refresh
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import Station
from chika.domain.service.geo import distance_meters
from chika.etl.mlit_client import MlitApiError, MlitClient, tiles_covering
from chika.etl.mlit_datasets import RIDERSHIP
from chika.etl.mlit_ridership import RidershipGroup, aggregate_by_group, parse_all

#: MLIT 자신이 같은 역으로 묶는 기준(300m 이내 그룹 코드 통합)과 맞춘다.
MATCH_RADIUS_M = 300.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/mlit_ridership.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/.cache"))
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 재수집")
    args = parser.parse_args()

    stations = _load_stations(args.stations)
    client = MlitClient(_api_key())

    features = _fetch(client, stations, args.cache_dir / "mlit_ridership_raw.json", args.refresh)
    points = parse_all(features)
    groups = aggregate_by_group(points)
    print(
        f"{RIDERSHIP.endpoint} ({RIDERSHIP.label}): {len(features)}건 -> "
        f"대표 그룹 {len(groups)}개"
    )

    if not groups:
        sys.exit("대표 레코드가 0건이다. 연도 필드나 대표코드 판별이 어긋났을 수 있다.")

    index: dict[str, dict[str, float]] = {}
    matched = 0
    for station in stations:
        group = _nearest(station, groups)
        if group is None:
            continue
        index[station.id] = {MetricKey.DAILY_RIDERSHIP.value: round(group.total, 1)}
        matched += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n호출 {client.calls_made}건 사용 (과금 없음)")
    print(f"역 {len(stations)}개 중 {matched}개 매칭 -> {args.out}")
    _summarise(index, stations)


def _nearest(station: Station, groups: list[RidershipGroup]) -> RidershipGroup | None:
    best: RidershipGroup | None = None
    best_distance = MATCH_RADIUS_M
    for group in groups:
        distance = distance_meters(station.lat, station.lon, group.lat, group.lon)
        if distance <= best_distance:
            best, best_distance = group, distance
    return best


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
    client: MlitClient, stations: list[Station], cache_path: Path, refresh: bool
) -> list[dict[str, object]]:
    if not refresh and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"캐시 사용: {cache_path} ({len(cached)}건)")
        return list(cached)

    margin_m = 1000.0 + MATCH_RADIUS_M
    tiles = tiles_covering([(s.lat, s.lon) for s in stations], RIDERSHIP.zoom, margin_m)
    print(f"{RIDERSHIP.endpoint}: 타일 {len(tiles)}개 (z={RIDERSHIP.zoom})")

    collected: list[dict[str, object]] = []
    try:
        for index, (x, y) in enumerate(tiles, start=1):
            collected.extend(client.features(RIDERSHIP, x, y))
            if index % 20 == 0 or index == len(tiles):
                print(f"  {index}/{len(tiles)} 타일, 누적 {len(collected):,}건")
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")
    return collected


def _summarise(index: dict[str, dict[str, float]], stations: list[Station]) -> None:
    names = {s.id: s.name_ja for s in stations}
    values = [v[MetricKey.DAILY_RIDERSHIP.value] for v in index.values()]
    ranked = sorted(
        index.items(), key=lambda kv: kv[1][MetricKey.DAILY_RIDERSHIP.value], reverse=True
    )

    def line(item: tuple[str, dict[str, float]]) -> str:
        station_id, v = item
        return f"{names[station_id]}({v[MetricKey.DAILY_RIDERSHIP.value]:,.0f}명/일)"

    print(f"  최다 유동인구: {', '.join(line(i) for i in ranked[:5])}")
    print(f"  중앙값: {statistics.median(values):,.0f}명/일")


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
