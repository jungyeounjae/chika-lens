"""지표 24(주거전용지역 비율) 인덱스 배치 — MLIT XKT002(用途地域).

호출 과금이 없다. 역세권 좌표를 덮는 타일로 용도지역 폴리곤을 받아
`ZoningIndex`(mlit_zoning.py)에 담고, 역마다 반경 800m 안에서 住居専用
지역(법적으로 상가·공장 금지)이 차지하는 면적 비율을 낸다. "조용함"을
직접 재지 못해서 만든 대리 지표다 — 자세한 이유는 mlit_zoning.py 참조.

사용법:

    export MLIT_API_KEY=...
    uv run --extra etl python -m chika.etl.build_zoning
    uv run --extra etl python -m chika.etl.build_zoning --refresh
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import STATION_RADIUS_METERS, Station
from chika.etl.mlit_client import MlitApiError, MlitClient, tiles_covering
from chika.etl.mlit_datasets import QUIET_ZONE_IDS, ZONING
from chika.etl.mlit_zoning import ZoningIndex, parse_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/mlit_zoning.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/.cache/mlit_zoning_raw.json"))
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 재수집")
    args = parser.parse_args()

    stations = _load_stations(args.stations)
    features = _fetch(stations, args.cache, args.refresh)
    zones = parse_all(features, QUIET_ZONE_IDS)
    print(
        f"{ZONING.endpoint} ({ZONING.label}): {len(features)}건 -> "
        f"구역 {len(zones)}개(중복 제거 후)"
    )

    if not zones:
        sys.exit("용도지역이 0건이다. 타일 범위나 엔드포인트가 어긋났을 수 있다.")

    index_tree = ZoningIndex(zones)
    index: dict[str, dict[str, float]] = {}
    for station in stations:
        ratio = index_tree.quiet_ratio_near(station.lat, station.lon, STATION_RADIUS_METERS)
        index[station.id] = {MetricKey.RESIDENTIAL_ZONE_RATIO.value: round(ratio, 4)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    _summarise(index, stations, args.out)


def _load_stations(path: Path) -> list[Station]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Station(
            id=row["id"], name_ja=row["name_ja"], ward=row["ward"],
            lat=float(row["lat"]), lon=float(row["lon"]), lines=tuple(row["lines"]),
        )
        for row in rows
    ]


def _fetch(stations: list[Station], cache: Path, refresh: bool) -> list[dict[str, object]]:
    if not refresh and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        print(f"캐시 사용: {cache} ({len(cached)}건)")
        return list(cached)

    margin_m = 1000.0 + STATION_RADIUS_METERS
    tiles = tiles_covering([(s.lat, s.lon) for s in stations], ZONING.zoom, margin_m)
    print(f"{ZONING.endpoint}: 타일 {len(tiles)}개 (z={ZONING.zoom})")

    client = MlitClient(_api_key())
    collected: list[dict[str, object]] = []
    try:
        for index, (x, y) in enumerate(tiles, start=1):
            collected.extend(client.features(ZONING, x, y))
            if index % 20 == 0 or index == len(tiles):
                print(f"  {index}/{len(tiles)} 타일, 누적 {len(collected):,}건")
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    print(f"호출 {client.calls_made}건 사용 (과금 없음)")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")
    return collected


def _summarise(index: dict[str, dict[str, float]], stations: list[Station], out: Path) -> None:
    names = {s.id: s.name_ja for s in stations}
    key = MetricKey.RESIDENTIAL_ZONE_RATIO.value
    values = [v[key] for v in index.values()]
    ranked = sorted(index.items(), key=lambda kv: kv[1][key], reverse=True)

    def line(item: tuple[str, dict[str, float]]) -> str:
        station_id, v = item
        return f"{names[station_id]}({v[key] * 100:.0f}%)"

    zeros = sum(1 for v in values if v == 0.0)
    print(f"\n역 {len(index)}개에 기록 -> {out}")
    print(f"  가장 조용한 편(주거전용 비율 높음): {', '.join(line(i) for i in ranked[:5])}")
    print(f"  주거전용지역 없음(0%): {zeros}개 역")
    print(f"  중앙값: {statistics.median(values) * 100:.1f}%")


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
