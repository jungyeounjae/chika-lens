"""`ParkPolygonSource` 포트의 실제 구현 — Overpass(OSM) 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와
같은 구조 — 배치가 아니라 요청 한 건을 위해 Overpass 를 실시간으로
호출한다.
"""

from __future__ import annotations

import json
import math

from chika.domain.model.polygon import ParkPolygon
from chika.etl.overpass_client import OverpassClient


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) — Overpass 가 요구하는 순서 그대로."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


class OverpassParkSource:
    def __init__(self, client: OverpassClient) -> None:
        self._client = client

    def polygons_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[ParkPolygon]:
        south, west, north, east = _bbox(lat, lon, radius_m)
        query = (
            "[out:json][timeout:25];"
            f'way["leisure"="park"]({south},{west},{north},{east});'
            "out geom;"
        )
        raw = self._client.query(query)
        data = json.loads(raw)

        polygons: list[ParkPolygon] = []
        for element in data.get("elements", []):
            geometry = element.get("geometry")
            if not isinstance(geometry, list) or len(geometry) < 3:
                continue
            coordinates = [[point["lon"], point["lat"]] for point in geometry]
            tags = element.get("tags") or {}
            polygons.append(
                ParkPolygon(
                    geometry={"type": "Polygon", "coordinates": [coordinates]},
                    name=tags.get("name"),
                )
            )
        return polygons
