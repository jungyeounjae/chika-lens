"""도쿄도 통계 → 지표 3 (구별 한국 국적 비율).

두 CSV를 地域コード로 조인한다:
  - 第3表 区市町村、国籍・地域別外国人人口 → 韓国 / 朝鮮 컬럼
  - 住民基本台帳による世帯と人口         → 人口総数（日本人＋外国人）
"""

import pytest

from chika.etl.tokyo_stats import (
    TOKYO_23_WARD_CODES,
    korean_ratio_by_ward,
    parse_foreign_population,
    parse_population,
)

_FOREIGN = """地域階層,地域コード,国・地域(人),総数,男,女,韓国,朝鮮,中国
0,13000,東京都総数,783701,394201,389500,90766,4019,299831
1,13100,区部,655945,330342,325603,77138,2799,262320
4,13101,千代田区,4344,2303,2041,506,5,2438
4,13104,新宿区,51357,26499,24858,9071,95,19778
4,13201,八王子市,12000,6000,6000,300,10,5000
"""

_POPULATION = """地域階層,地域コード,地域,人口総数（日本人＋外国人）,前月増減,人口／日本人／総数
0,13000,総数,14077552,-6134,13293851
1,13100,区部,9796723,-5921,9140778
4,13101,千代田区,69139,-135,64795
4,13104,新宿区,352000,120,300643
4,13201,八王子市,560000,10,548000
"""


# --- 외국인 인구 파싱 ---


def test_parses_korean_and_chosen_columns_per_ward() -> None:
    rows = parse_foreign_population(_FOREIGN)
    assert rows["13101"].korean == 506
    assert rows["13101"].chosen == 5


def test_aggregate_rows_are_excluded() -> None:
    """東京都総数·区部 같은 집계행이 섞이면 비율이 망가진다."""
    rows = parse_foreign_population(_FOREIGN)
    assert "13000" not in rows
    assert "13100" not in rows


def test_non_ward_municipalities_are_excluded() -> None:
    """지표는 23구 단위다. 八王子市는 분석 범위 밖이다."""
    rows = parse_foreign_population(_FOREIGN)
    assert "13201" not in rows


def test_ward_name_is_kept() -> None:
    assert parse_foreign_population(_FOREIGN)["13104"].ward == "新宿区"


# --- 총인구 파싱 ---


def test_parses_total_population_per_ward() -> None:
    assert parse_population(_POPULATION)["13101"] == 69139


def test_population_excludes_aggregates_and_non_wards() -> None:
    pop = parse_population(_POPULATION)
    assert "13000" not in pop
    assert "13100" not in pop
    assert "13201" not in pop


# --- 비율 계산 ---


def test_ratio_is_korean_over_total_population() -> None:
    ratio = korean_ratio_by_ward(_FOREIGN, _POPULATION)
    # 千代田区: (506 + 5) / 69139
    assert ratio["千代田区"] == pytest.approx(511 / 69139)


def test_chosen_nationality_is_counted_with_korean() -> None:
    """在日コリアン 중 朝鮮 등록자도 한국계 커뮤니티 신호다.

    지표가 재려는 것은 '한국 커뮤니티가 있는가'이고, 등록 국적 구분은
    그 목적에 대해 자의적이다.
    """
    ratio = korean_ratio_by_ward(_FOREIGN, _POPULATION)
    assert ratio["新宿区"] == pytest.approx((9071 + 95) / 352000)


def test_the_result_is_keyed_by_ward_name_to_match_the_station_master() -> None:
    """역 마스터의 ward 필드가 '新宿区' 형태라 그대로 조인 가능해야 한다."""
    assert set(korean_ratio_by_ward(_FOREIGN, _POPULATION)) == {"千代田区", "新宿区"}


def test_a_ward_missing_from_either_file_is_omitted_not_zero() -> None:
    """0으로 채우면 '한국인이 없는 구'가 되어 거짓말이 된다."""
    foreign_only = _FOREIGN
    population_without_shinjuku = "\n".join(
        line for line in _POPULATION.splitlines() if "新宿区" not in line
    )
    ratio = korean_ratio_by_ward(foreign_only, population_without_shinjuku)
    assert "新宿区" not in ratio
    assert "千代田区" in ratio


def test_zero_population_does_not_divide_by_zero() -> None:
    broken = _POPULATION.replace("69139", "0")
    ratio = korean_ratio_by_ward(_FOREIGN, broken)
    assert "千代田区" not in ratio


def test_there_are_23_ward_codes() -> None:
    assert len(TOKYO_23_WARD_CODES) == 23


def test_bom_and_crlf_are_tolerated() -> None:
    """도쿄도 CSV는 BOM과 CRLF를 쓴다."""
    ratio = korean_ratio_by_ward(
        "﻿" + _FOREIGN.replace("\n", "\r\n"),
        "﻿" + _POPULATION.replace("\n", "\r\n"),
    )
    assert ratio["千代田区"] == pytest.approx(511 / 69139)
