"""재해(hazard) 폴리곤 모델."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HazardPolygon:
    """재해 폴리곤.

    MLIT 등 외부 소스에서 조회한 원본 재해 데이터(홍수, 지진, 지반 등).
    """

    layer: str
    geometry: dict[str, Any]
    severity: float
    label: str
