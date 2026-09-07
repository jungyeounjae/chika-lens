"""지표 2 배치 — 한국 식자재·미용 시설 (1회성).

489역 × 2쿼리 = 978콜. Text Search Pro SKU의 월 5,000 무료 한도 안이다.
식자재점 분포는 달마다 바뀌지 않으므로 매월 돌릴 이유가 없다.

  export GOOGLE_MAPS_API_KEY=...
  uv run python -m chika.etl.build_korean_shops --dry-run
  uv run python -m chika.etl.build_korean_shops
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.etl.aggregate_batch import Checkpoint
from chika.etl.places_text import KOREAN_QUERIES, TextSearchClient, count_korean_shops

QUERY_KEY = MetricKey.KOREAN_GROCERY.value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/korean_shops.json"))
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("data/.cache/korean_shops_progress.jsonl")
    )
    parser.add_argument("--max-calls", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stations = json.loads(args.stations.read_text(encoding="utf-8"))
    checkpoint = Checkpoint(args.checkpoint)
    done = {station_id for station_id, key in checkpoint.done_keys() if key == QUERY_KEY}
    pending = [s for s in stations if s["id"] not in done]
    calls = len(pending) * len(KOREAN_QUERIES)

    print(f"역 {len(stations):,}  이미 완료 {len(done):,}  남은 역 {len(pending):,}")
    print(f"이번에 쓸 콜: {calls:,} / 상한 {args.max_calls:,}")
    if calls > args.max_calls:
        sys.exit("예산 초과로 중단한다 (콜은 쓰지 않았다). --max-calls 로 올린다.")
    if args.dry_run:
        print("--dry-run 이므로 여기서 끝낸다.")
        return

    client = TextSearchClient(_api_key())
    try:
        for index, station in enumerate(pending, start=1):
            count = count_korean_shops(client, station["lat"], station["lon"])
            checkpoint.record(station["id"], QUERY_KEY, count)
            if index % 50 == 0 or index == len(pending):
                print(f"  {index:,}/{len(pending):,}  {station['name_ja']}={count}")
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"\n중단: {exc}", file=sys.stderr)
        print(f"진행분은 {args.checkpoint} 에 남았다. 같은 명령으로 이어받는다.", file=sys.stderr)
        raise SystemExit(1) from exc

    counts = checkpoint.counts()
    shop_index = {
        station["id"]: {QUERY_KEY: float(counts[(station["id"], QUERY_KEY)])}
        for station in stations
        if (station["id"], QUERY_KEY) in counts
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(shop_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n호출 {client.calls_made:,}건 사용 -> {args.out} ({len(shop_index):,}개 역)")


def _api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        sys.exit("GOOGLE_MAPS_API_KEY 가 비어 있다.")
    return key


if __name__ == "__main__":
    main()
