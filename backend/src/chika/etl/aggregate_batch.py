"""Aggregate API 배치의 순수 로직 — 이어받기, 예산 가드, 결과 접기.

네트워크를 타지 않으므로 전부 단위 테스트된다. HTTP는 aggregate_client가 맡는다.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.etl.aggregate_queries import CORE_QUERIES, CUISINE_BASKET, AggregateQuery

#: 무료 한도. 넘으면 실제 돈이 나가므로 기본값으로 막는다.
FREE_TIER_CALLS = 5000

WorkItem = tuple[str, AggregateQuery]
CountKey = tuple[str, str]


def remaining_budget(used_this_month: int) -> int:
    """이번 달 남은 무료 콜 수.

    `--max-calls` 는 "남은 작업량"만 보고 "이미 쓴 양"을 모른다. 배치를 여러 번
    돌리면 매번 통과시키고 결국 한도를 넘는다 — 실제로 그렇게 429를 맞았다.
    사용량은 Cloud Monitoring 에서 조회한다 (스펙 §3.1.1).
    """
    return max(0, FREE_TIER_CALLS - used_this_month)


class BudgetExceeded(RuntimeError):
    """예산을 넘는 작업을 요청받았다. 콜을 하나도 쓰기 전에 던진다."""


def effective_type_count(counts: Sequence[int]) -> float:
    """섀넌 엔트로피의 유효 종 수 exp(H) — 지표 10.

    '몇 종류가 있나'는 도쿄에서 거의 모든 역이 만점이라 변별이 안 된다(스펙 §6.2.1).
    한 타입이 압도하면 1에 가깝고, 고르게 분포하면 타입 수에 가까워진다.
    """
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        share = count / total
        entropy -= share * math.log(share)
    return math.exp(entropy)


@dataclass(frozen=True)
class Checkpoint:
    """(역, 쿼리) 단위 진행 기록.

    JSONL append 전용이라 중간에 프로세스가 죽어도 마지막 줄만 잘린다.
    부트스트랩이 8,313콜이고 무료 한도가 5,000이라, 실패한 배치를 처음부터
    다시 돌릴 여유가 없다 — 이 파일이 그걸 막는다.
    """

    path: Path

    def record(self, station_id: str, query_key: str, count: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"station_id": station_id, "query": query_key, "count": count},
            ensure_ascii=False,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _rows(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # 잘린 마지막 줄. 그 한 건만 다시 받으면 된다.
                continue
        return rows

    def done_keys(self) -> set[CountKey]:
        return {(str(r["station_id"]), str(r["query"])) for r in self._rows()}

    def counts(self) -> dict[CountKey, int]:
        return {
            (str(r["station_id"]), str(r["query"])): int(str(r["count"]))
            for r in self._rows()
        }


def pending_work(
    station_ids: Sequence[str],
    queries: Sequence[AggregateQuery],
    done: set[CountKey],
    max_calls: int = FREE_TIER_CALLS,
) -> list[WorkItem]:
    """아직 받지 않은 (역, 쿼리) 쌍을 결정적 순서로 돌려준다.

    예산을 넘으면 콜을 하나도 쓰기 전에 막는다 — 반쯤 진행된 뒤에 청구서로
    알게 되는 것이 최악이다.
    """
    pending = [
        (station_id, query)
        for station_id in sorted(station_ids)
        for query in queries
        if (station_id, query.key) not in done
    ]
    if len(pending) > max_calls:
        raise BudgetExceeded(
            f"남은 작업 {len(pending):,}콜이 상한 {max_calls:,}콜을 넘는다. "
            f"--max-calls 로 올리거나 배치를 나눠 돌린다."
        )
    return pending


def fold_results(
    station_ids: Sequence[str],
    counts: Mapping[CountKey, int],
) -> list[RawMetrics]:
    """수집한 카운트를 지표별 원시값으로 접는다.

    이 배치가 담당하지 않는 지표(MLIT·도쿄도 통계)와, 조회가 끝나지 않은 지표는
    None으로 남는다. 정규화가 결측 플래그를 세워 화면이 '데이터 없음'을 표기한다.
    """
    core_keys = {query.key for query in CORE_QUERIES}
    results: list[RawMetrics] = []

    for station_id in station_ids:
        values: dict[MetricKey, float | None] = dict.fromkeys(MetricKey, None)

        for key in core_keys:
            count = counts.get((station_id, key))
            if count is not None:
                values[MetricKey(key)] = float(count)

        basket = [counts.get((station_id, q.key)) for q in CUISINE_BASKET]
        if all(count is not None for count in basket):
            values[MetricKey.RESTAURANT_VARIETY] = effective_type_count(
                [int(count) for count in basket if count is not None]
            )

        results.append(RawMetrics(station_id=station_id, values=values))
    return results
