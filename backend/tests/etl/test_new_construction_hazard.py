"""HazardPolygon 목록 -> 층별(최고 위험도) 안전성 요약."""

from __future__ import annotations

from chika.domain.model.polygon import HazardPolygon
from chika.etl.new_construction_hazard import summarize_hazards


def _hazard(layer: str, severity: float, label: str) -> HazardPolygon:
    return HazardPolygon(layer=layer, geometry={}, severity=severity, label=label)


def test_a_single_layer_with_one_polygon_is_summarized_as_is() -> None:
    summary = summarize_hazards([_hazard("flood", 0.5, "3.0m~5.0m")])
    assert summary["flood"].severity == 0.5
    assert summary["flood"].label == "3.0m~5.0m"


def test_multiple_polygons_in_the_same_layer_keep_the_worst_severity() -> None:
    """반경 안에 같은 레이어 폴리곤이 여러 개 걸리면(경계 근처) 가장 위험한 것을
    대표값으로 삼는다 — 평균을 내면 위험이 희석되어 보인다."""
    summary = summarize_hazards(
        [
            _hazard("sediment", 0.4, "옐로존(지정완료)"),
            _hazard("sediment", 1.0, "레드존(지정완료)"),
        ]
    )
    assert summary["sediment"].severity == 1.0
    assert summary["sediment"].label == "레드존(지정완료)"


def test_layers_with_no_polygon_are_absent_not_zero() -> None:
    """반경 안에 해당 레이어가 하나도 안 잡히면 '안전(0)'이 아니라 '결측'이다 —
    키 자체가 없어야 호출부가 '이 레이어는 데이터가 없다'를 구분할 수 있다."""
    summary = summarize_hazards([_hazard("flood", 0.2, "0m~0.5m")])
    assert "tsunami" not in summary
    assert "liquefaction" not in summary


def test_an_empty_polygon_list_is_an_empty_summary() -> None:
    assert summarize_hazards([]) == {}
