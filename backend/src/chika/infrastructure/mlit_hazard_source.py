"""`HazardPolygonSource` 포트의 실제 구현 — MLIT 실시간 조회 + shapely 거리 계산.

domain/application은 이 파일의 존재를 모른다 — shapely·MlitClient 같은 구체
의존은 여기 안에 가둔다(Clean Architecture, README "계층 규칙"). 배치가
아니라 요청 한 건을 위해 실시간으로 MLIT을 호출한다(호출 과금 없음) —
489역 전체를 이렇게 부르면 안 된다, 그건 `chika.etl.build_hazards`의 몫이다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from chika.domain.model.polygon import HazardPolygon
from chika.etl.mlit_client import MlitClient, tiles_covering
from chika.etl.mlit_datasets import (
    FLOOD,
    LIQUEFACTION,
    SEDIMENT_HAZARD,
    STORM_SURGE,
    TSUNAMI,
    MlitDataset,
)
from chika.etl.mlit_hazards import (
    flood_severity,
    liquefaction_severity,
    nearest_distance_m,
    sediment_severity,
    storm_surge_severity,
    tsunami_severity,
)

#: 국토수치정보 공식 코드표(`water_depth_code.html`, 확인 2026-09-11).
FLOOD_DEPTH_LABEL: dict[int, str] = {
    1: "0m~0.5m",
    2: "0.5m~3.0m",
    3: "3.0m~5.0m",
    4: "5.0m~10.0m",
    5: "10.0m~20.0m",
    6: "20.0m 이상",
}

#: mlit_hazards.py 의 등급 설명(1/3=Yellow, 2/4=Red)과 같다.
SEDIMENT_LABEL: dict[int, str] = {
    1: "옐로존(급경사지 붕괴위험, 지정완료)",
    2: "레드존(급경사지 붕괴위험, 지정완료)",
    3: "옐로존(지정 전·조사단계)",
    4: "레드존(지정 전·조사단계)",
}

#: mlit_hazards.py 의 _STORM_SURGE_BANDS(공식 확인된 7단계)를 그대로 옮긴다.
STORM_SURGE_LABEL: dict[str, str] = {
    "0.3m未満": "0.3m 미만",
    "0.3m以上0.5m未満": "0.3m~0.5m",
    "0.5m以上1m未満": "0.5m~1m",
    "1m以上3m未満": "1m~3m",
    "3m以上5m未満": "3m~5m",
    "5m以上10m未満": "5m~10m",
    "10m以上20m未満": "10m~20m",
}


def _liquefaction_label(level: int) -> str:
    return f"액상화 위험도 {level}/5 (낮을수록 위험)"


def _storm_surge_label(band: str) -> str:
    return STORM_SURGE_LABEL.get(band, band)


def _tsunami_label(band: str) -> str:
    # 도도부현마다 구간 표기가 달라(神奈川 7단계·千葉 6단계 등, mlit_hazards.py
    # 참고) 고정 코드표가 없다 — zoning_massing의 use_area_ja와 같은 이유로
    # 원문을 그대로 낸다.
    return band


_SeverityFn = Callable[[Any], "float | None"]
_LabelFn = Callable[[Any], str]

_LAYERS: tuple[tuple[MlitDataset, str, str, _SeverityFn, _LabelFn], ...] = (
    (FLOOD, "flood", "A31a_205", flood_severity, lambda raw: FLOOD_DEPTH_LABEL.get(raw, str(raw))),
    (
        SEDIMENT_HAZARD,
        "sediment",
        "A33_002",
        sediment_severity,
        lambda raw: SEDIMENT_LABEL.get(raw, str(raw)),
    ),
    (
        LIQUEFACTION,
        "liquefaction",
        "liquefaction_tendency_level",
        liquefaction_severity,
        _liquefaction_label,
    ),
    (STORM_SURGE, "storm_surge", "A49_003", storm_surge_severity, _storm_surge_label),
    (TSUNAMI, "tsunami", "A40_003", tsunami_severity, _tsunami_label),
)


def _dissolve(polygons: list[HazardPolygon]) -> list[HazardPolygon]:
    """MLIT 원본은 벡터 타일의 작은 그리드 셀 단위로 온다 — 같은
    (layer, severity, label) 끼리 인접 셀을 하나로 합쳐 지도에서 격자로
    보이지 않게 한다. 등급이 다르면 정보 손실이 되므로 합치지 않는다."""
    groups: dict[tuple[str, float, str], list[HazardPolygon]] = {}
    for polygon in polygons:
        key = (polygon.layer, polygon.severity, polygon.label)
        groups.setdefault(key, []).append(polygon)

    dissolved: list[HazardPolygon] = []
    for (layer, severity, label), group in groups.items():
        merged = unary_union([shape(p.geometry) for p in group])
        dissolved.append(
            HazardPolygon(layer=layer, geometry=mapping(merged), severity=severity, label=label)
        )
    return dissolved


class MlitHazardPolygonSource:
    def __init__(self, client: MlitClient) -> None:
        self._client = client

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[HazardPolygon]:
        polygons: list[HazardPolygon] = []
        for dataset, layer, field, severity_fn, label_fn in _LAYERS:
            tiles = tiles_covering([(lat, lon)], dataset.zoom, radius_m)
            seen_ids: set[str] = set()
            for x, y in tiles:
                for feature in self._client.features(dataset, x, y):
                    properties = feature.get("properties")
                    if not isinstance(properties, dict):
                        continue
                    feature_id = str(properties.get("_id", ""))
                    if feature_id and feature_id in seen_ids:
                        continue
                    raw = properties.get(field)
                    if raw is None:
                        continue
                    severity = severity_fn(raw)
                    if severity is None:
                        continue
                    geometry_dict = feature.get("geometry")
                    if not isinstance(geometry_dict, dict):
                        continue
                    distance = nearest_distance_m(lat, lon, shape(geometry_dict))
                    if distance > radius_m:
                        continue
                    if feature_id:
                        seen_ids.add(feature_id)
                    polygons.append(
                        HazardPolygon(
                            layer=layer,
                            geometry=geometry_dict,
                            severity=severity,
                            label=label_fn(raw),
                        )
                    )
        return _dissolve(polygons)
