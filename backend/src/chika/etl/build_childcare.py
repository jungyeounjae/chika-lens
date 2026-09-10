"""지표 11(육아·교육) 인덱스 배치 — MLIT 不動産情報ライブラリ.

Google Aggregate 를 대체한다. 호출 과금이 없고 (z=13 기준 59타일 × 2데이터셋
= 118콜), 인가 시설의 공식 등록부라 학원·어학원이 섞이지 않는다.

받은 원본은 `data/.cache/` 에만 두고 커밋하지 않는다 — MLIT 에 제출한 이용
목적대로, 개별 시설 레코드는 재배포하지 않고 역세권 집계값만 쓴다 (스펙 §3.1.2).

사용법:

    export MLIT_API_KEY=...
    uv run python -m chika.etl.build_childcare
    uv run python -m chika.etl.build_childcare --refresh   # 캐시 무시하고 재수집
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import STATION_RADIUS_METERS, Station
from chika.etl.mlit_childcare import (
    Facility,
    count_near,
    deduplicate,
    parse_preschool,
    parse_school,
)
from chika.etl.mlit_client import MlitApiError, MlitClient, tiles_covering
from chika.etl.mlit_datasets import (
    ELEMENTARY_SCHOOL_KINDS,
    MIDDLE_SCHOOL_KINDS,
    PRESCHOOL,
    SCHOOL,
    TILE_ZOOM,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/mlit_childcare.json"))
    parser.add_argument(
        "--cache", type=Path, default=Path("data/.cache/mlit_childcare_raw.json")
    )
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 재수집")
    args = parser.parse_args()

    rows = json.loads(args.stations.read_text(encoding="utf-8"))
    stations = [
        Station(
            id=row["id"], name_ja=row["name_ja"], ward=row["ward"],
            lat=float(row["lat"]), lon=float(row["lon"]), lines=tuple(row["lines"]),
        )
        for row in rows
    ]

    raw = _load_cache(args.cache) if not args.refresh else None
    if raw is None:
        raw = _fetch(stations, args.cache)
    else:
        print(f"캐시 사용: {args.cache}")

    # 타일 경계가 겹쳐서 같은 시설이 여러 번 오므로, 데이터셋마다 따로
    # 중복 제거한다 — 두 데이터셋의 시설 id 는 서로 다른 출처라 안 섞인다.
    preschools = deduplicate(f for item in raw[PRESCHOOL.endpoint] if (f := parse_preschool(item)))
    schools = deduplicate(f for item in raw[SCHOOL.endpoint] if (f := parse_school(item)))
    _report(raw, preschools + schools)

    if not preschools and not schools:
        sys.exit("집계 대상 시설이 0건이다. 필터가 실제 종별과 어긋났을 수 있다.")

    # 유치원·보육시설(11), 초등학교(22), 중학교(23) — 원래 하나로 합쳐 세던 것을
    # 종별로 나눈다. 義務教育学校는 초등·중학 양쪽에 다 들어간다(mlit_datasets.py).
    elementary = [f for f in schools if f.kind in ELEMENTARY_SCHOOL_KINDS]
    middle = [f for f in schools if f.kind in MIDDLE_SCHOOL_KINDS]

    counts_by_metric = {
        MetricKey.CHILDCARE_EDUCATION: count_near(stations, preschools, STATION_RADIUS_METERS),
        MetricKey.ELEMENTARY_SCHOOL: count_near(stations, elementary, STATION_RADIUS_METERS),
        MetricKey.MIDDLE_SCHOOL: count_near(stations, middle, STATION_RADIUS_METERS),
    }
    index: dict[str, dict[str, float]] = {station.id: {} for station in stations}
    for metric, counts in counts_by_metric.items():
        for station_id, count in counts.items():
            index[station_id][metric.value] = float(count)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    names = {s.id: s.name_ja for s in stations}
    print(f"\n역 {len(index)}개에 기록 -> {args.out}")
    for metric, counts in counts_by_metric.items():
        by_station = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        top = ", ".join(f"{names[i]} {c}" for i, c in by_station[:5])
        zeros = sum(1 for _, c in by_station if c == 0)
        print(f"  {metric.value}: 최다 {top} / 0건 {zeros}개 역")


def _fetch(
    stations: list[Station], cache: Path
) -> dict[str, list[dict[str, object]]]:
    client = MlitClient(_api_key())
    tiles = tiles_covering([(s.lat, s.lon) for s in stations], TILE_ZOOM)
    print(f"타일 {len(tiles)}개 × 데이터셋 2개 = {len(tiles) * 2}콜 (과금 없음)")

    raw: dict[str, list[dict[str, object]]] = {}
    try:
        for dataset in (PRESCHOOL, SCHOOL):
            collected: list[dict[str, object]] = []
            for index, (x, y) in enumerate(tiles, start=1):
                collected.extend(client.features(dataset, x, y, TILE_ZOOM))
                if index % 20 == 0 or index == len(tiles):
                    print(f"  {dataset.endpoint} {dataset.label}  {index}/{len(tiles)}")
            raw[dataset.endpoint] = collected
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    print(f"호출 {client.calls_made}건 사용, 원본은 {cache} 에만 둔다")
    return raw


def _load_cache(cache: Path) -> dict[str, list[dict[str, object]]] | None:
    if not cache.exists():
        return None
    loaded: dict[str, list[dict[str, object]]] = json.loads(
        cache.read_text(encoding="utf-8")
    )
    if PRESCHOOL.endpoint not in loaded or SCHOOL.endpoint not in loaded:
        return None
    return loaded


def _report(
    raw: dict[str, list[dict[str, object]]], facilities: list[Facility]
) -> None:
    """무엇이 세어졌는지 보여준다 — 구성이 조용히 바뀌면 지표도 조용히 바뀐다."""
    print("\n받은 원본:")
    for endpoint, items in raw.items():
        print(f"  {endpoint}: {len(items):,}건")
    kinds = collections.Counter(f.kind for f in facilities)
    print(f"\n집계 대상 {len(facilities):,}곳 (중복 제거 후):")
    for kind, n in kinds.most_common():
        print(f"  {kind:<12} {n:,}")


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
