"""비용 보호 — 스펙 §9가 '처음부터 넣는다'고 못박은 요구사항.

공개 시 대화 한 번에 OpenAI 비용이 나가므로, IP당 속도 제한과 전체 일일 상한을
둘 다 둔다. 하나만으로는 부족하다: IP 제한만 있으면 분산 요청에 뚫리고,
일일 상한만 있으면 한 사람이 하루치를 다 쓸 수 있다.
"""

import pytest

from chika.interface.api.guards import CostGuard, DailyCapReached, RateLimited


def _guard(**kw: object) -> CostGuard:
    defaults: dict[str, object] = {
        "per_ip_per_minute": 3,
        "daily_total": 10,
        "now": lambda: 0.0,
    }
    defaults.update(kw)
    return CostGuard(**defaults)  # type: ignore[arg-type]


def test_requests_under_the_limit_pass() -> None:
    guard = _guard()
    for _ in range(3):
        guard.check("1.1.1.1")


def test_the_fourth_request_in_a_minute_is_refused() -> None:
    guard = _guard()
    for _ in range(3):
        guard.check("1.1.1.1")
    with pytest.raises(RateLimited):
        guard.check("1.1.1.1")


def test_the_window_slides() -> None:
    clock = [0.0]
    guard = _guard(now=lambda: clock[0])
    for _ in range(3):
        guard.check("1.1.1.1")
    clock[0] = 61.0
    guard.check("1.1.1.1")


def test_limits_are_per_ip() -> None:
    guard = _guard()
    for _ in range(3):
        guard.check("1.1.1.1")
    guard.check("2.2.2.2")


def test_the_daily_cap_covers_every_ip_together() -> None:
    """IP 제한만 있으면 분산 요청에 뚫린다. 전체 상한이 마지막 방어선이다."""
    clock = [0.0]
    guard = _guard(per_ip_per_minute=100, daily_total=5, now=lambda: clock[0])
    for i in range(5):
        guard.check(f"1.1.1.{i}")
    with pytest.raises(DailyCapReached):
        guard.check("9.9.9.9")


def test_the_daily_cap_resets_after_a_day() -> None:
    clock = [0.0]
    guard = _guard(per_ip_per_minute=100, daily_total=2, now=lambda: clock[0])
    guard.check("1.1.1.1")
    guard.check("1.1.1.1")
    clock[0] = 86_401.0
    guard.check("1.1.1.1")


def test_a_refused_request_does_not_consume_daily_budget() -> None:
    """속도 제한에 걸린 요청이 일일 예산을 깎으면, 재시도만으로 하루치가 날아간다."""
    guard = _guard(per_ip_per_minute=1, daily_total=5)
    guard.check("1.1.1.1")
    for _ in range(3):
        with pytest.raises(RateLimited):
            guard.check("1.1.1.1")
    assert guard.remaining_today() == 4


def test_remaining_today_reports_the_budget() -> None:
    guard = _guard(daily_total=10)
    guard.check("1.1.1.1")
    assert guard.remaining_today() == 9


def test_the_error_says_when_to_retry() -> None:
    guard = _guard(per_ip_per_minute=1)
    guard.check("1.1.1.1")
    with pytest.raises(RateLimited) as exc:
        guard.check("1.1.1.1")
    assert exc.value.retry_after_seconds > 0
