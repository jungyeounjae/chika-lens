"""HazardPolygon 목록(한 좌표 주변 조회 결과) -> 레이어별 최고 위험도 요약.

MlitHazardPolygonSource.polygons_near()가 반환하는 원본 목록은 반경 안에 걸린
폴리곤 전부를 담고 있어(경계 근처에서는 같은 레이어가 여러 개 걸릴 수 있다),
그대로 저장하면 "이 물건이 안전한가"를 한눈에 읽을 수 없다. 레이어마다 가장
위험한 값 하나로 접는다 — 평균을 내면 위험이 희석되어 보인다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.polygon import HazardPolygon


@dataclass(frozen=True)
class HazardSummary:
    layer: str
    severity: float
    label: str


def summarize_hazards(polygons: Sequence[HazardPolygon]) -> dict[str, HazardSummary]:
    """레이어별로 severity가 가장 큰(=가장 위험한) 폴리곤 하나만 남긴다.
    반경 안에 레이어가 하나도 안 잡히면 그 레이어의 키 자체가 없다 — '안전'과
    '데이터 없음'을 헷갈리지 않기 위해서다."""
    best: dict[str, HazardSummary] = {}
    for polygon in polygons:
        current = best.get(polygon.layer)
        if current is None or polygon.severity > current.severity:
            best[polygon.layer] = HazardSummary(
                layer=polygon.layer, severity=polygon.severity, label=polygon.label
            )
    return best
