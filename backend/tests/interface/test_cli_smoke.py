from chika.interface.agent.actions import act_rank_areas, act_set_criteria
from chika.interface.cli import build_demo_session, run_demo


def test_demo_session_ranks_end_to_end() -> None:
    state = build_demo_session()
    act_set_criteria(
        state,
        korean_life=4.0, daily_convenience=2.0, quality_of_life=1.0,
        family=0.0, cost_risk=2.0, budget_max_yen=160_000,
    )
    result = act_rank_areas(state, limit=5)
    assert len(result["areas"]) == 5
    assert result["areas"][0]["score"] >= result["areas"][-1]["score"]


def test_run_demo_prints_a_ranking(capsys) -> None:  # type: ignore[no-untyped-def]
    run_demo()
    output = capsys.readouterr().out
    assert "1." in output
    assert "근거" in output
    assert "구 단위 지표" in output  # is_ward_resolution 라벨이 실제로 찍힌다
    assert "데이터 없음" in output  # missing_metrics 라벨이 실제로 찍힌다
