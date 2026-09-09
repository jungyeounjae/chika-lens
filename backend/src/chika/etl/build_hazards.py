"""지표 14(재해위험) 인덱스 배치 — MLIT 액상화·홍수·해일·토사재해 4개 레이어.

호출 과금이 없다. 4개 데이터셋을 역세권 좌표를 덮는 타일로 받아
`HazardIndex`(mlit_hazards.py)에 합치고, 역마다 반경 안 최댓값 위험도를 낸다.

FLOOD(XKT026)만 z=15 를 요구해 타일 수가 다른 3개보다 훨씬 많다 — z=13 대비
한 변이 4배로 쪼개져 타일 개수가 16배가 된다. 데이터셋마다 캐시 파일을
따로 둔다 (스펙 §3.1.2 — 원본은 `data/.cache/`에만, 커밋하지 않는다).

z=15 는 실측으로 타일당 6초 안팎이 걸렸다 — 레이트리밋(0.2초)이 아니라
응답 자체가 느리다. 766타일 전부 받으면 2시간을 넘긴다. `--max-tiles` 로
일부만 받아 파이프라인을 먼저 검증할 수 있다 — 잘라낸 결과는 캐시에 쓰지
않는다. 캐시에 남으면 다음 "전체 실행"이 부분 데이터를 완전한 데이터로
오인해 재수집을 건너뛴다.

사용법:

    export MLIT_API_KEY=...
    uv run --extra etl python -m chika.etl.build_hazards
    uv run --extra etl python -m chika.etl.build_hazards --refresh
    uv run --extra etl python -m chika.etl.build_hazards --max-tiles 40   # 부분 수집
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
from chika.etl.mlit_client import MlitApiError, MlitClient, tiles_covering
from chika.etl.mlit_datasets import (
    FLOOD,
    LIQUEFACTION,
    SEDIMENT_HAZARD,
    STORM_SURGE,
    MlitDataset,
)
from chika.etl.mlit_hazards import DECAY_M, HazardIndex, parse_all

#: 배치 레이어 키 -> (데이터셋, 파서가 보는 layer 문자열, 캐시 파일명).
_LAYERS: tuple[tuple[MlitDataset, str, str], ...] = (
    (LIQUEFACTION, "liquefaction", "mlit_hazard_liquefaction_raw.json"),
    (FLOOD, "flood", "mlit_hazard_flood_raw.json"),
    (STORM_SURGE, "storm_surge", "mlit_hazard_storm_surge_raw.json"),
    (SEDIMENT_HAZARD, "sediment", "mlit_hazard_sediment_raw.json"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/mlit_hazards.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/.cache"))
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 재수집")
    parser.add_argument(
        "--max-tiles",
        type=int,
        default=None,
        help="레이어당 타일 상한. 검증용 부분 수집 — 결과는 캐시에 쓰지 않는다",
    )
    args = parser.parse_args()

    stations = _load_stations(args.stations)
    client = MlitClient(_api_key())

    zones = []
    for dataset, layer, cache_name in _LAYERS:
        cache_path = args.cache_dir / cache_name
        features = _fetch_layer(
            client, stations, dataset, cache_path, args.refresh, args.max_tiles
        )
        parsed = parse_all(features, layer)
        print(f"{dataset.endpoint} ({dataset.label}): {len(features)}건 -> 유효 {len(parsed)}건")
        zones.extend(parsed)

    if args.max_tiles is not None:
        print(
            f"\n*** 부분 수집(--max-tiles {args.max_tiles}) — 전체 커버리지가 아니다. "
            f"{args.out} 를 그대로 두지 말고 전체 실행 후 덮어써야 한다. ***"
        )

    if not zones:
        sys.exit("4개 레이어 전부 0건이다. 타일 범위나 엔드포인트가 어긋났을 수 있다.")

    index_tree = HazardIndex(zones)
    index: dict[str, dict[str, float]] = {}
    for station in stations:
        risk = index_tree.risk_near(station.lat, station.lon)
        index[station.id] = {MetricKey.DISASTER_RISK.value: round(risk, 4)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n호출 {client.calls_made}건 사용 (과금 없음)")
    _summarise(index, stations, args.out)


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


def _fetch_layer(
    client: MlitClient,
    stations: list[Station],
    dataset: MlitDataset,
    cache_path: Path,
    refresh: bool,
    max_tiles: int | None = None,
) -> list[dict[str, object]]:
    # 근접 위험(DECAY_M)까지 봐야 하므로 타일 여유를 그만큼 더 둔다 — 역이
    # 타일 경계에 붙어 있으면 근접 폴리곤이 옆 타일에 있을 수 있다.
    margin_m = 1000.0 + DECAY_M
    all_tiles = tiles_covering([(s.lat, s.lon) for s in stations], dataset.zoom, margin_m)
    # 이 레이어가 실제로 잘리는지가 기준이다 — "max_tiles 가 켜졌는가"가
    # 아니다. 그걸로 가르면 이미 온전한 캐시가 있는 다른 레이어까지 재수집한다.
    truncated = max_tiles is not None and max_tiles < len(all_tiles)

    if not truncated and not refresh and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"캐시 사용: {cache_path} ({len(cached)}건)")
        return list(cached)

    tiles = all_tiles[:max_tiles] if truncated else all_tiles
    print(f"{dataset.endpoint}: 타일 {len(tiles)}개 (z={dataset.zoom}, 전체 {len(all_tiles)}개 중)")

    collected: list[dict[str, object]] = []
    try:
        for index, (x, y) in enumerate(tiles, start=1):
            collected.extend(client.features(dataset, x, y))
            if index % 20 == 0 or index == len(tiles):
                print(f"  {index}/{len(tiles)} 타일, 누적 {len(collected):,}건")
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    if truncated:
        return collected

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")
    return collected


def _summarise(index: dict[str, dict[str, float]], stations: list[Station], out: Path) -> None:
    names = {s.id: s.name_ja for s in stations}
    wards = {s.id: s.ward for s in stations}
    values = [v[MetricKey.DISASTER_RISK.value] for v in index.values()]
    ranked = sorted(
        index.items(), key=lambda kv: kv[1][MetricKey.DISASTER_RISK.value], reverse=True
    )

    def line(item: tuple[str, dict[str, float]]) -> str:
        station_id, v = item
        return f"{names[station_id]}({wards[station_id]}) {v[MetricKey.DISASTER_RISK.value]:.2f}"

    at_risk = sum(1 for v in values if v > 0)
    print(f"\n역 {len(index)}개에 기록 -> {out}")
    print(f"  위험 신호 있음(>0): {at_risk}개 / 위험 없음(=0): {len(values) - at_risk}개")
    print(f"  최고 위험: {', '.join(line(i) for i in ranked[:5])}")
    print(f"  중앙값: {statistics.median(values):.3f}")


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
