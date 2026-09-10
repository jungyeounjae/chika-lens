"""Aggregate API 지표 인덱스 배치 (이어받기 지원).

부트스트랩은 489역 × 17콜 = 8,313콜이고 무료 한도는 월 5,000콜이다.
실패한 배치를 처음부터 다시 돌릴 여유가 없으므로, 조회 한 건마다 체크포인트에
append하고 재실행 시 남은 것만 이어받는다.

사용법:

    export GOOGLE_MAPS_API_KEY=...
    uv run python -m chika.etl.build_metrics --core        # 코어 지표 (월 1회)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.etl.aggregate_batch import (
    FREE_TIER_CALLS,
    BudgetExceeded,
    Checkpoint,
    fold_results,
    pending_work,
    remaining_budget,
)
from chika.etl.aggregate_client import AggregateApiError, AggregateClient
from chika.etl.aggregate_queries import CORE_QUERIES, AggregateQuery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="store_true", help="코어 지표")
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--out", type=Path, default=Path("data/metrics.json"))
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("data/.cache/aggregate_progress.jsonl")
    )
    parser.add_argument(
        "--max-calls", type=int, default=None,
        help="이번 실행의 콜 상한. 기본은 당월 잔여 무료 한도(자동 조회)",
    )
    parser.add_argument(
        "--used-this-month", type=int, default=None,
        help="당월 사용량을 직접 지정한다 (조회 실패 시)",
    )
    parser.add_argument("--dry-run", action="store_true", help="콜 수만 계산하고 끝낸다")
    args = parser.parse_args()

    if not args.core:
        parser.error("--core 를 지정한다")

    queries: list[AggregateQuery] = list(CORE_QUERIES)

    stations = json.loads(args.stations.read_text(encoding="utf-8"))
    coords = {s["id"]: (s["lat"], s["lon"]) for s in stations}
    names = {s["id"]: s["name_ja"] for s in stations}

    max_calls = args.max_calls
    if max_calls is None:
        used = args.used_this_month
        if used is None:
            used = _used_this_month()
        if used is None:
            sys.exit(
                "당월 사용량을 조회하지 못했다. --used-this-month 나 --max-calls 를 지정한다.\n"
                "  (gcloud auth 가 되어 있어야 Cloud Monitoring 을 읽을 수 있다)"
            )
        max_calls = remaining_budget(used)
        print(f"당월 사용 {used:,} / {FREE_TIER_CALLS:,}  잔여 {max_calls:,}")

    checkpoint = Checkpoint(args.checkpoint)
    done = checkpoint.done_keys()
    try:
        pending = pending_work(list(coords), queries, done, max_calls=max_calls)
    except BudgetExceeded as exc:
        sys.exit(f"예산 초과로 중단한다 (콜은 쓰지 않았다).\n  {exc}")

    print(f"역 {len(coords):,}  쿼리 {len(queries)}  이미 완료 {len(done):,}건")
    print(f"이번에 쓸 콜: {len(pending):,} / 상한 {max_calls:,}")
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


def _used_this_month() -> int | None:
    """Cloud Monitoring 에서 당월 Aggregate 요청 수를 읽는다.

    무료 한도는 월 단위이므로 배치가 스스로 확인해야 한다. 조회에 실패하면
    추측하지 않고 사용자에게 넘긴다 — 틀린 값으로 예산을 계산하면
    가드가 있는 척만 하게 된다.
    """
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    params = urllib.parse.urlencode(
        {
            "filter": (
                'metric.type="serviceruntime.googleapis.com/api/request_count" '
                'AND resource.labels.service="areainsights.googleapis.com"'
            ),
            "interval.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval.endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aggregation.alignmentPeriod": "2592000s",
            "aggregation.perSeriesAligner": "ALIGN_SUM",
        }
    )
    try:
        # gcloud 는 PATH 의 python3 로 자기 코드를 돌린다. uv 가 venv(3.12)를 PATH
        # 앞에 두면 gcloud 448 이 3.12 에서 제거된 `imp` 를 import 하다 죽는다.
        # venv 를 PATH 에서 빼고 Python 관련 변수를 지워 시스템 인터프리터를 쓰게 한다.
        venv = os.environ.get("VIRTUAL_ENV", "")
        path = os.pathsep.join(
            p for p in os.environ.get("PATH", "").split(os.pathsep)
            if not (venv and p.startswith(venv))
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONEXECUTABLE"}
        }
        env["PATH"] = path
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=30, check=True, env=env,
        ).stdout.strip()
        project = os.environ.get("CHIKA_GCP_PROJECT", "chika-lens")
        request = urllib.request.Request(
            f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries?{params}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 조회 실패는 치명적이지 않다, 사용자에게 넘긴다
        return None

    return sum(
        int(point["value"].get("int64Value", 0))
        for series in payload.get("timeSeries", [])
        for point in series.get("points", [])
    )


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
