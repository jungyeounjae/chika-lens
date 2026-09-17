"""랜드마크 지오코딩 결과 값 객체."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LandmarkMatch:
    name: str
    lat: float
    lon: float
