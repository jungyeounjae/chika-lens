"""원본 MLIT Polygon 값 객체 — 3D 시각화용(스펙 §3.1.2 정정, 2026-09-11).

`geometry`는 GeoJSON dict를 그대로 들고 있는다 — domain은 shapely 같은
외부 라이브러리를 몰라야 하므로(Clean Architecture, README "계층 규칙"),
좌표 계산이 필요한 거리 필터링·심각도 변환은 infrastructure 어댑터가 끝내고
그 결과만 여기 담아 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HazardPolygon:
    layer: str  # "flood" | "sediment" | "liquefaction" | "storm_surge" | "tsunami"
    geometry: dict[str, object]
    severity: float
    label: str


@dataclass(frozen=True)
class ZoningPolygon:
    geometry: dict[str, object]
    youto_id: int
    use_area_ja: str
    height_m: float


@dataclass(frozen=True)
class ParkPolygon:
    geometry: dict[str, object]
    #: OSM 에 이름이 없는 공원도 있다(실측 확인, 2026-09-14). 지어내지 않는다.
    name: str | None
