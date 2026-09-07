"""세션 저장 — 스펙 §5.5의 '조건 되돌리기'가 여기에 걸린다.

"예산 12만엔으로 낮추면?"이 오면 이전 SearchCriteria를 유지한 채 해당 필드만
교체해야 한다. 세션이 매 요청마다 초기화되면 이 유스케이스가 성립하지 않는다.
"""

import pytest

from chika.interface.api.sessions import SessionStore


def _store(**kw: object) -> SessionStore:
    defaults: dict[str, object] = {
        "factory": lambda: object(),
        "max_sessions": 3,
        "ttl_seconds": 100.0,
        "now": lambda: 0.0,
    }
    defaults.update(kw)
    return SessionStore(**defaults)  # type: ignore[arg-type]


def test_the_same_id_gets_the_same_session() -> None:
    store = _store()
    assert store.get("s1") is store.get("s1")


def test_different_ids_get_different_sessions() -> None:
    store = _store()
    assert store.get("s1") is not store.get("s2")


def test_a_session_is_built_by_the_factory_only_once() -> None:
    calls = [0]

    def factory() -> object:
        calls[0] += 1
        return object()

    store = _store(factory=factory)
    store.get("s1")
    store.get("s1")
    assert calls[0] == 1


def test_an_expired_session_is_rebuilt() -> None:
    clock = [0.0]
    store = _store(ttl_seconds=10.0, now=lambda: clock[0])
    first = store.get("s1")
    clock[0] = 11.0
    assert store.get("s1") is not first


def test_activity_refreshes_the_ttl() -> None:
    """대화 중인 세션이 TTL로 사라지면 조건이 초기화된다."""
    clock = [0.0]
    store = _store(ttl_seconds=10.0, now=lambda: clock[0])
    first = store.get("s1")
    clock[0] = 8.0
    store.get("s1")
    clock[0] = 15.0
    assert store.get("s1") is first


def test_the_oldest_session_is_evicted_when_full() -> None:
    """세션이 무한히 쌓이면 메모리가 샌다."""
    clock = [0.0]
    store = _store(max_sessions=2, now=lambda: clock[0])
    first = store.get("s1")
    clock[0] = 1.0
    store.get("s2")
    clock[0] = 2.0
    store.get("s3")
    assert store.get("s1") is not first


def test_the_most_recently_used_session_survives_eviction() -> None:
    clock = [0.0]
    store = _store(max_sessions=2, now=lambda: clock[0])
    first = store.get("s1")
    clock[0] = 1.0
    store.get("s2")
    clock[0] = 2.0
    store.get("s1")  # s1 을 다시 써서 최신으로 만든다
    clock[0] = 3.0
    store.get("s3")  # s2 가 밀려나야 한다
    assert store.get("s1") is first


def test_size_reports_live_sessions() -> None:
    store = _store()
    store.get("s1")
    store.get("s2")
    assert store.size() == 2


def test_an_empty_session_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="session id"):
        _store().get("")
