"""Aggregate API 지표 인덱스 배치 (이어받기 지원).

부트스트랩은 489역 × 17콜 = 8,313콜이고 무료 한도는 월 5,000콜이다.
실패한 배치를 처음부터 다시 돌릴 여유가 없으므로, 조회 한 건마다 체크포인트에
append하고 재실행 시 남은 것만 이어받는다.

사용법:

    export GOOGLE_MAPS_API_KEY=...
    uv run python -m chika.etl.build_metrics --core        # 코어 9지표 (월 1회)
    uv run python -m chika.etl.build_metrics --diversity   # 요리 8종 (6개월 1회)
    uv run python -m chika.etl.build_metrics --core --diversity --max-calls 9000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.etl.aggregate_batch import (
    FREE_TIER_CALLS,
    BudgetExceeded,
    Checkpoint,
    fold_results,
    pending_work,
)
from chika.etl.aggregate_client import AggregateApiError, AggregateClient
from chika.etl.aggregate_queries import CORE_QUERIES, CUISINE_BASKET, AggregateQuery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="store_true", help="코어 9지표")
    parser.add_argument("--diversity", action="store_true", help="요리 바스켓 8종")
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/metrics.json"))
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("data/.cache/aggregate_progress.jsonl")
    )
    parser.add_argument(
        "--max-calls", type=int, default=FREE_TIER_CALLS,
        help=f"이번 실행의 콜 상한 (기본 {FREE_TIER_CALLS:,} = 무료 한도)",
    )
    parser.add_argument("--dry-run", action="store_true", help="콜 수만 계산하고 끝낸다")
    args = parser.parse_args()

    if not (args.core or args.diversity):
        parser.error("--core / --diversity 중 하나 이상을 지정한다")

    queries: list[AggregateQuery] = []
    if args.core:
        queries.extend(CORE_QUERIES)
    if args.diversity:
        queries.extend(CUISINE_BASKET)

    stations = json.loads(args.stations.read_text(encoding="utf-8"))
    coords = {s["id"]: (s["lat"], s["lon"]) for s in stations}
    names = {s["id"]: s["name_ja"] for s in stations}

    checkpoint = Checkpoint(args.checkpoint)
    done = checkpoint.done_keys()
    try:
        pending = pending_work(list(coords), queries, done, max_calls=args.max_calls)
    except BudgetExceeded as exc:
        sys.exit(f"예산 초과로 중단한다 (콜은 쓰지 않았다).\n  {exc}")

    print(f"역 {len(coords):,}  쿼리 {len(queries)}  이미 완료 {len(done):,}건")
    print(f"이번에 쓸 콜: {len(pending):,} / 상한 {args.max_calls:,}")
    if args.dry_run:
        print("--dry-run 이므로 여기서 끝낸다.")
        return
    if not pending:
        print("남은 작업이 없다. 인덱스만 다시 접는다.")

    client = AggregateClient(_api_key())
    try:
        for index, (station_id, query) in enumerate(pending, start=1):
            lat, lon = coords[station_id]
            count = client.count(query, lat, lon)
            checkpoint.record(station_id, query.key, count)
            if index % 100 == 0 or index == len(pending):
                print(f"  {index:,}/{len(pending):,}  {names[station_id]} {query.key}={count}")
    except (AggregateApiError, KeyboardInterrupt) as exc:
        print(f"\n중단: {exc}", file=sys.stderr)
        print(
            f"{client.calls_made:,}건은 체크포인트에 남았다. 같은 명령을 다시 실행하면 "
            f"이어받는다: {args.checkpoint}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    _write_index(args.out, list(coords), checkpoint)
    print(f"\n호출 {client.calls_made:,}건 사용 -> {args.out}")


def _write_index(out: Path, station_ids: list[str], checkpoint: Checkpoint) -> None:
    raws = fold_results(station_ids, checkpoint.counts())
    index = {
        raw.station_id: {
            key.value: value
            for key in MetricKey
            if (value := raw.get(key)) is not None
        }
        for raw in raws
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    measured = sum(len(row) for row in index.values())
    print(f"지표값 {measured:,}건을 {len(index):,}개 역에 기록")


def _api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY 가 비어 있다. export 로 넘긴다.")
    return key


if __name__ == "__main__":
    main()
