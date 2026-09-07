"""도쿄도 통계 → 지표 3 (구별 한국 국적 비율).

두 CSV를 `地域コード`로 조인한다.

- 第3表 区市町村、国籍・地域別外国人人口 → `韓国` / `朝鮮` 컬럼
  https://www.toukei.metro.tokyo.lg.jp/gaikoku/2026/ga26ev0300.csv
- 住民基本台帳による世帯と人口 → `人口総数（日本人＋外国人）`
  https://www.toukei.metro.tokyo.lg.jp/juukim/2026/jm261v0000_1.csv

이 지표는 **구 단위**다. 같은 구 안의 모든 역이 같은 값을 갖는다. 스펙 §3.2에 따라
낮은 가중치의 배경 보정으로만 쓰고, 화면에 "이 지표는 구 단위입니다"를 명시한다
(`is_ward_resolution` 플래그가 그 통로다).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass

#: 도쿄 23구의 地域コード. 集計행(13000 총수, 13100 구부)과 市部를 걸러내는 데 쓴다.
TOKYO_23_WARD_CODES: frozenset[str] = frozenset(
    f"131{n:02d}" for n in range(1, 24)
)


@dataclass(frozen=True)
class ForeignPopulation:
    ward: str
    korean: int
    chosen: int

    @property
    def korean_total(self) -> int:
        """`韓国` + `朝鮮`.

        지표가 재려는 것은 '한국 커뮤니티가 있는가'이고, 재일 코리안의 등록 국적
        구분(韓国/朝鮮)은 그 목적에 대해 자의적이다. 둘을 합쳐야 실제 커뮤니티
        규모에 가깝다.
        """
        return self.korean + self.chosen


def _rows(text: str) -> list[dict[str, str]]:
    # 도쿄도 CSV는 BOM과 CRLF를 쓴다.
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def _ward_code(row: Mapping[str, str]) -> str | None:
    code = (row.get("地域コード") or "").strip()
    return code if code in TOKYO_23_WARD_CODES else None


def _as_int(value: str | None) -> int | None:
    cleaned = (value or "").strip().replace(",", "")
    if not cleaned or not cleaned.lstrip("-").isdigit():
        return None
    return int(cleaned)


def parse_foreign_population(text: str) -> dict[str, ForeignPopulation]:
    """第3表 → 地域コード별 한국·조선 국적자 수. 23구만 남긴다."""
    result: dict[str, ForeignPopulation] = {}
    for row in _rows(text):
        code = _ward_code(row)
        if code is None:
            continue
        korean = _as_int(row.get("韓国"))
        chosen = _as_int(row.get("朝鮮"))
        ward = (row.get("国・地域(人)") or "").strip()
        if korean is None or chosen is None or not ward:
            continue
        result[code] = ForeignPopulation(ward=ward, korean=korean, chosen=chosen)
    return result


def parse_population(text: str) -> dict[str, int]:
    """住民基本台帳 → 地域コード별 총인구(일본인＋외국인). 23구만 남긴다."""
    result: dict[str, int] = {}
    for row in _rows(text):
        code = _ward_code(row)
        if code is None:
            continue
        total = _as_int(row.get("人口総数（日本人＋外国人）"))
        if total is not None:
            result[code] = total
    return result


def korean_ratio_by_ward(foreign_csv: str, population_csv: str) -> dict[str, float]:
    """구 이름 → 한국 국적자 비율.

    역 마스터의 `ward` 필드가 "新宿区" 형태이므로 그대로 조인된다.

    어느 한쪽 파일에 없는 구는 **결과에서 빠진다.** 0으로 채우면 "한국인이 없는
    구"가 되어 거짓말이 된다 — 정규화가 결측 플래그를 세워 화면에 "데이터 없음"으로
    표기하게 하는 것이 옳다.
    """
    foreign = parse_foreign_population(foreign_csv)
    population = parse_population(population_csv)

    ratio: dict[str, float] = {}
    for code, entry in foreign.items():
        total = population.get(code)
        if not total:  # 없거나 0
            continue
        ratio[entry.ward] = entry.korean_total / total
    return ratio
