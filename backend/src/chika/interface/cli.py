"""Phase 0 종료 증거. OpenAI 키 없이 조건 → 랭킹 → 근거를 한 번 출력한다."""

from __future__ import annotations

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.actions import act_explain_area, act_rank_areas, act_set_criteria
from chika.interface.agent.state import SessionState, UseCases


def build_demo_session(count: int = 40) -> SessionState:
    stations, raws, commute, prices = build_seed(count=count)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
        )
    )


def run_demo() -> None:
    state = build_demo_session()
    act_set_criteria(
        state,
        korean_life=4.0,
        daily_convenience=2.0,
        quality_of_life=1.0,
        family=0.0,
        cost_risk=2.0,
        budget_max_yen=160_000,
        household="single",
    )
    ranking = act_rank_areas(state, limit=5)

    print("=== Chika Lens Phase 0 (시드 데이터) ===")
    print("조건: 한국 생활 중시, 예산 16만엔 이하, 1인 가구\n")

    for index, area in enumerate(ranking["areas"], start=1):
        rent = f"{area['rent_yen']:,}엔" if area["rent_yen"] is not None else "데이터 없음"
        print(f"{index}. {area['name_ko']} ({area['ward']})  점수 {area['score']}  월세 {rent}")

    top_id = ranking["areas"][0]["station_id"]
    detail = act_explain_area(state, top_id)
    print(f"\n[1위 근거] {detail['name_ko']}")
    for item in detail["strengths"]:
        note = " (구 단위 지표)" if item["is_ward_resolution"] else ""
        print(f"  + {item['metric']}: 상위 {100 - item['percentile']:.0f}%{note}")
    for item in detail["weaknesses"]:
        print(f"  - {item['metric']}: 상위 {100 - item['percentile']:.0f}%")
    if detail["missing_metrics"]:
        print(f"  ! 데이터 없음: {', '.join(detail['missing_metrics'])}")


if __name__ == "__main__":
    run_demo()
