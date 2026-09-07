"""조건 → 랭킹 → 근거를 한 번 출력하는 데모. OpenAI 키가 필요 없다.

기본은 시드 데이터다. `--real` 을 주면 Aggregate 배치가 만든 실제 인덱스를 읽는다.
시세·통근은 아직 소스가 없어 비어 있다 — 화면에 '데이터 없음'으로 나간다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.infrastructure.file_metrics import FileAreaMetricsRepository
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


def build_real_session(
    stations_path: Path = Path("data/stations.json"),
    metrics_path: Path = Path("data/metrics.json"),
    ward_stats_path: Path = Path("data/ward_stats.json"),
) -> SessionState:
    """Aggregate 배치가 만든 실제 인덱스로 세션을 구성한다.

    시세·통근 리포지토리는 빈 Fake다 — MLIT 어댑터와 역간 소요시간 테이블이
    아직 없다. 예산·통근 조건을 걸지 않으면 랭킹은 정상 동작하고, 월세는
    화면에 '데이터 없음'으로 나간다. 없는 값을 지어내는 것보다 낫다.
    """
    areas = FileAreaMetricsRepository(stations_path, metrics_path, ward_stats_path)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository({}), FakePriceRepository({})),
            explain=ExplainArea(areas, FakePriceRepository({})),
            compare=CompareAreas(areas),
        )
    )


def run_demo(state: SessionState | None = None, header: str = "시드 데이터") -> None:
    state = state or build_demo_session()
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

    print(f"=== Chika Lens ({header}) ===")
    print("조건: 한국 생활 중시, 예산 16만엔 이하, 1인 가구\n")

    for index, area in enumerate(ranking["areas"], start=1):
        rent = f"{area['rent_yen']:,}엔" if area["rent_yen"] is not None else "데이터 없음"
        print(f"{index}. {area['name_ja']} ({area['ward']})  점수 {area['score']}  월세 {rent}")

    if not ranking["areas"]:
        print("\n조건에 맞는 역세권이 없습니다.")
        return

    top_id = ranking["areas"][0]["station_id"]
    detail = act_explain_area(state, top_id)
    print(f"\n[1위 근거] {detail['name_ja']}")
    for item in detail["strengths"]:
        note = " (구 단위 지표)" if item["is_ward_resolution"] else ""
        print(f"  + {item['metric']}: 상위 {100 - item['percentile']:.0f}%{note}")
    for item in detail["weaknesses"]:
        print(f"  - {item['metric']}: 상위 {100 - item['percentile']:.0f}%")
    if detail["missing_metrics"]:
        print(f"  ! 데이터 없음: {', '.join(detail['missing_metrics'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real", action="store_true", help="Aggregate 배치가 만든 실제 인덱스를 쓴다"
    )
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument("--metrics", type=Path, default=Path("data/metrics.json"))
    args = parser.parse_args()

    if args.real:
        run_demo(build_real_session(args.stations, args.metrics), header="실데이터")
    else:
        run_demo()


if __name__ == "__main__":
    main()
