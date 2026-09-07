"""도쿄도 통계 → 구 단위 지표 인덱스 (지표 3).

Aggregate API 인덱스와 파일을 분리한다. 갱신 주기가 다르고(연 1회 vs 월 1회),
무엇보다 **출처가 달라 재배포 권리가 다르다** — 도쿄도 오픈데이터는 출처 표기
조건으로 재배포 가능하므로 이 산출물은 커밋한다 (스펙 §3.1.2).

사전 준비 (수동 다운로드):

  第3表 区市町村、国籍・地域別外国人人口
    https://www.toukei.metro.tokyo.lg.jp/gaikoku/2026/ga26ev0300.csv
  住民基本台帳による世帯と人口
    https://www.toukei.metro.tokyo.lg.jp/juukim/2026/jm261v0000_1.csv

사용법:

  uv run python -m chika.etl.build_ward_stats \\
      --foreign ga26ev0300.csv --population jm261v0000_1.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chika.domain.model.metrics import MetricKey
from chika.etl.tokyo_stats import korean_ratio_by_ward

TOKYO_23_WARD_COUNT = 23


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foreign", type=Path, required=True, help="第3表 CSV")
    parser.add_argument("--population", type=Path, required=True, help="住民基本台帳 CSV")
    parser.add_argument("--out", type=Path, default=Path("data/ward_stats.json"))
    args = parser.parse_args()

    ratio = korean_ratio_by_ward(
        args.foreign.read_text(encoding="utf-8"),
        args.population.read_text(encoding="utf-8"),
    )
    if len(ratio) != TOKYO_23_WARD_COUNT:
        # 23개가 아니면 집계행 필터나 컬럼명이 바뀐 것이다. 조용히 넘기면
        # 일부 구가 결측으로 남아 원인 없이 순위가 흔들린다.
        sys.exit(
            f"구 {len(ratio)}개만 산출됐다 (기대 {TOKYO_23_WARD_COUNT}개). "
            f"입력 CSV의 컬럼명이나 地域コード 체계가 바뀌었을 수 있다.\n"
            f"  산출된 구: {sorted(ratio)}"
        )

    index = {
        ward: {MetricKey.KOREAN_RESIDENT_RATIO.value: round(value, 6)}
        for ward, value in sorted(ratio.items())
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    top = max(ratio.items(), key=lambda kv: kv[1])
    low = min(ratio.items(), key=lambda kv: kv[1])
    print(f"구 {len(index)}개 -> {args.out}")
    print(f"  최고 {top[0]} {top[1]*100:.3f}%   최저 {low[0]} {low[1]*100:.3f}%")


if __name__ == "__main__":
    main()
