"""실데이터 세션 배선 — 파일에서 읽은 지표로 세션을 구성한다."""

import json
from pathlib import Path

import pytest

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.weights import Dial, DialSettings
from chika.interface.agent.actions import act_rank_areas, act_set_criteria
from chika.interface.cli import build_real_session

_STATIONS = [
    {"id": "st_a", "name_ja": "新大久保", "ward": "新宿区",
     "lat": 35.7009, "lon": 139.7003, "lines": ["山手線"]},
    {"id": "st_b", "name_ja": "世田谷", "ward": "世田谷区",
     "lat": 35.6466, "lon": 139.6491, "lines": ["世田谷線"]},
]
_METRICS = {
    "st_a": {"korean_restaurant": 234.0, "cafe": 163.0, "supermarket": 24.0},
    "st_b": {"korean_restaurant": 1.0, "cafe": 31.0, "supermarket": 1.0},
}


def _paths(tmp_path: Path, metrics: dict | None = None) -> tuple[Path, Path]:
    sp = tmp_path / "stations.json"
    mp = tmp_path / "metrics.json"
    sp.write_text(json.dumps(_STATIONS, ensure_ascii=False), encoding="utf-8")
    if metrics is not None:
        mp.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
    return sp, mp


def test_real_session_ranks_from_the_metrics_file(tmp_path: Path) -> None:
    state = build_real_session(*_paths(tmp_path, _METRICS))
    act_set_criteria(
        state, korean_life=5.0, daily_convenience=0.0,
        quality_of_life=0.0, family=0.0, cost_risk=0.0,
    )
    result = act_rank_areas(state, limit=2)
    assert [a["name_ja"] for a in result["areas"]] == ["新大久保", "世田谷"]


def test_metrics_absent_from_the_file_stay_missing(tmp_path: Path) -> None:
    """MLIT 담당 지표는 아직 없다. '데이터 없음'으로 나가야 한다."""
    state = build_real_session(*_paths(tmp_path, _METRICS))
    act_set_criteria(
        state, korean_life=1.0, daily_convenience=1.0,
        quality_of_life=1.0, family=1.0, cost_risk=1.0,
    )
    result = act_rank_areas(state, limit=1)
    keys = {m["metric"] for m in result["areas"][0]["missing_metrics"]}
    assert "price_level" in keys


def test_rent_is_unknown_without_a_price_source(tmp_path: Path) -> None:
    state = build_real_session(*_paths(tmp_path, _METRICS))
    act_set_criteria(
        state, korean_life=1.0, daily_convenience=1.0,
        quality_of_life=1.0, family=1.0, cost_risk=1.0,
    )
    assert act_rank_areas(state, limit=1)["areas"][0]["rent_yen"] is None


def test_a_missing_metrics_file_fails_loudly(tmp_path: Path) -> None:
    state = build_real_session(*_paths(tmp_path, metrics=None))
    act_set_criteria(
        state, korean_life=1.0, daily_convenience=1.0,
        quality_of_life=1.0, family=1.0, cost_risk=1.0,
    )
    with pytest.raises(FileNotFoundError, match="metrics.json"):
        act_rank_areas(state)


def test_criteria_still_flow_through_the_same_use_cases(tmp_path: Path) -> None:
    """실데이터로 바뀌어도 다이얼이 순위를 뒤집는 성질은 같아야 한다."""
    state = build_real_session(*_paths(tmp_path, _METRICS))
    korean = SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 5.0}))
    assert state.usecases.rank.execute(korean, limit=1)[0].station.name_ja == "新大久保"
