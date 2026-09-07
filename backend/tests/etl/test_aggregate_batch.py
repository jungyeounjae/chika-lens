import json
from pathlib import Path

import pytest

from chika.domain.model.metrics import MetricKey
from chika.etl.aggregate_batch import (
    BudgetExceeded,
    Checkpoint,
    effective_type_count,
    fold_results,
    pending_work,
)
from chika.etl.aggregate_queries import CORE_QUERIES, CUISINE_BASKET, AggregateQuery

# --- 유효 종 수 ---


def test_effective_type_count_of_even_distribution_is_the_type_count() -> None:
    assert effective_type_count([10, 10, 10, 10]) == pytest.approx(4.0)


def test_effective_type_count_of_a_monopoly_is_one() -> None:
    assert effective_type_count([100, 0, 0, 0]) == pytest.approx(1.0)


def test_effective_type_count_of_nothing_is_zero() -> None:
    assert effective_type_count([0, 0, 0]) == 0.0


def test_effective_type_count_matches_the_nakano_measurement() -> None:
    """스펙 §6.2.1의 실측값. 일식 70% 편중이라 8종이 전부 있어도 3.13이다."""
    assert effective_type_count([455, 41, 39, 9, 6, 24, 59, 20]) == pytest.approx(3.13, abs=0.01)


# --- 체크포인트 ---


def _checkpoint(tmp_path: Path) -> Checkpoint:
    return Checkpoint(tmp_path / "progress.jsonl")


def test_a_fresh_checkpoint_has_nothing_done(tmp_path: Path) -> None:
    assert _checkpoint(tmp_path).done_keys() == set()


def test_recorded_work_is_remembered(tmp_path: Path) -> None:
    cp = _checkpoint(tmp_path)
    cp.record("st_a", "cafe", 12)
    cp.record("st_b", "cafe", 7)
    assert cp.done_keys() == {("st_a", "cafe"), ("st_b", "cafe")}


def test_a_new_checkpoint_object_reads_what_a_previous_run_wrote(tmp_path: Path) -> None:
    _checkpoint(tmp_path).record("st_a", "cafe", 12)
    assert _checkpoint(tmp_path).done_keys() == {("st_a", "cafe")}


def test_a_truncated_last_line_is_discarded_not_fatal(tmp_path: Path) -> None:
    """프로세스가 append 도중에 죽으면 마지막 줄이 잘린다. 나머지는 살아야 한다."""
    path = tmp_path / "progress.jsonl"
    path.write_text(
        json.dumps({"station_id": "st_a", "query": "cafe", "count": 12}) + "\n" + '{"stat',
        encoding="utf-8",
    )
    assert Checkpoint(path).done_keys() == {("st_a", "cafe")}


def test_counts_are_recoverable_for_folding(tmp_path: Path) -> None:
    cp = _checkpoint(tmp_path)
    cp.record("st_a", "cafe", 12)
    assert cp.counts()[("st_a", "cafe")] == 12


# --- 남은 작업 계산 ---


def test_pending_work_is_every_pair_when_nothing_is_done() -> None:
    pending = pending_work(["st_a", "st_b"], CORE_QUERIES, done=set())
    assert len(pending) == 2 * len(CORE_QUERIES)


def test_pending_work_skips_what_the_checkpoint_already_has() -> None:
    done = {("st_a", CORE_QUERIES[0].key)}
    pending = pending_work(["st_a", "st_b"], CORE_QUERIES, done=done)
    assert len(pending) == 2 * len(CORE_QUERIES) - 1
    assert ("st_a", CORE_QUERIES[0].key) not in {(s, q.key) for s, q in pending}


def test_pending_work_is_ordered_by_station_then_query() -> None:
    """실행 순서가 결정적이어야 이어받기가 예측 가능하다."""
    pending = pending_work(["st_b", "st_a"], CORE_QUERIES[:2], done=set())
    assert [s for s, _ in pending] == ["st_a", "st_a", "st_b", "st_b"]


def test_pending_work_over_budget_raises_before_spending_anything() -> None:
    with pytest.raises(BudgetExceeded, match="4,401"):
        pending_work(
            [f"st_{i}" for i in range(489)], CORE_QUERIES, done=set(), max_calls=100
        )


# --- 결과 접기 ---


def test_fold_turns_core_counts_into_raw_metrics() -> None:
    counts = {("st_a", q.key): 7 for q in CORE_QUERIES}
    raws = fold_results(["st_a"], counts)
    assert len(raws) == 1
    assert raws[0].station_id == "st_a"
    assert raws[0].get(MetricKey.CAFE) == 7.0


def test_fold_leaves_unmeasured_metrics_as_none() -> None:
    """MLIT·통계 담당 지표는 이 배치가 채우지 않는다. 결측으로 남아야 한다."""
    counts = {("st_a", q.key): 3 for q in CORE_QUERIES}
    raws = fold_results(["st_a"], counts)
    assert raws[0].get(MetricKey.PRICE_LEVEL) is None
    assert raws[0].get(MetricKey.KOREAN_RESIDENT_RATIO) is None


def test_fold_computes_diversity_from_the_cuisine_basket() -> None:
    counts: dict[tuple[str, str], int] = {(("st_a"), q.key): 3 for q in CORE_QUERIES}
    counts.update({("st_a", q.key): 10 for q in CUISINE_BASKET})
    raws = fold_results(["st_a"], counts)
    assert raws[0].get(MetricKey.RESTAURANT_VARIETY) == pytest.approx(8.0)


def test_fold_leaves_diversity_missing_when_the_basket_was_not_run() -> None:
    counts = {("st_a", q.key): 3 for q in CORE_QUERIES}
    raws = fold_results(["st_a"], counts)
    assert raws[0].get(MetricKey.RESTAURANT_VARIETY) is None


def test_fold_leaves_a_metric_missing_when_its_query_never_completed() -> None:
    counts = {("st_a", q.key): 5 for q in CORE_QUERIES if q.key != MetricKey.PARK}
    raws = fold_results(["st_a"], counts)
    assert raws[0].get(MetricKey.PARK) is None
    assert raws[0].get(MetricKey.CAFE) == 5.0


def test_fold_preserves_station_order() -> None:
    counts = {("st_b", q.key): 1 for q in CORE_QUERIES}
    counts.update({("st_a", q.key): 2 for q in CORE_QUERIES})
    raws = fold_results(["st_b", "st_a"], counts)
    assert [r.station_id for r in raws] == ["st_b", "st_a"]


def test_unknown_query_key_is_ignored_not_fatal() -> None:
    """쿼리 정의가 바뀌어도 옛 체크포인트가 배치를 죽이면 안 된다."""
    counts: dict[tuple[str, str], int] = {("st_a", "no_such_query"): 99}
    counts.update({("st_a", q.key): 1 for q in CORE_QUERIES})
    raws = fold_results(["st_a"], counts)
    assert raws[0].get(MetricKey.CAFE) == 1.0


def test_query_keys_cover_every_aggregate_metric() -> None:
    """CORE_QUERIES가 스펙의 Aggregate 담당 지표를 빠짐없이 덮는지."""
    covered = {q.key for q in CORE_QUERIES}
    expected = {
        MetricKey.KOREAN_RESTAURANT, MetricKey.SUPERMARKET, MetricKey.CONVENIENCE_STORE,
        MetricKey.HEALTHCARE, MetricKey.CAFE, MetricKey.PARK, MetricKey.FITNESS,
        MetricKey.CHILD_FRIENDLY_VENUE, MetricKey.NUISANCE_VENUE,
    }
    assert covered == expected


def test_no_duplicate_query_keys() -> None:
    keys = [q.key for q in (*CORE_QUERIES, *CUISINE_BASKET)]
    assert len(keys) == len(set(keys))


def test_aggregate_query_is_frozen() -> None:
    q = AggregateQuery("x", ("cafe",))
    with pytest.raises(AttributeError):
        q.key = "y"  # type: ignore[misc]
