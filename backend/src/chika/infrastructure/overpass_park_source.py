"""`ParkPolygonSource` 포트의 실제 구현 — Overpass(OSM) 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와
같은 구조 — 배치가 아니라 요청 한 건을 위해 Overpass 를 실시간으로
호출한다.
"""

from __future__ import annotations

import json
import math

from chika.domain.model.polygon import ParkPolygon
from chika.etl.overpass_client import OverpassClient, OverpassFetchError


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) — Overpass 가 요구하는 순서 그대로."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


Point = tuple[float, float]  # (lon, lat)


def _stitch_rings(segments: list[list[Point]]) -> list[list[Point]]:
    """outer 멤버 way 조각들을 끝점이 맞는 것끼리 이어 닫힌 링으로 조립한다.

    작은 공원은 대개 way 하나가 이미 닫혀 있다(그대로 링 하나). 신주쿠교엔처럼
    큰 공원은 outer 가 여러 way 조각으로 나뉘어 있어 이어 붙여야 한다.
    끝까지 안 닫히는 조각은 조용히 버린다(예외로 전체 조회를 죽이지 않는다) —
    구멍(inner)은 이번 범위에서 다루지 않는다: 프런트(polygonThreeLayer.ts)가
    이미 "외곽 링만 쓴다(구멍 무시)"고 명시해 뒀으니, 백엔드에서 정확히
    뚫어봐야 화면에 반영되지 않는다.
    """
    remaining = [seg for seg in segments if len(seg) >= 2]
    rings: list[list[Point]] = []
    while remaining:
        ring = list(remaining.pop(0))
        progress = True
        while ring[0] != ring[-1] and progress:
            progress = False
            for i, seg in enumerate(remaining):
                if seg[0] == ring[-1]:
                    ring.extend(seg[1:])
                    remaining.pop(i)
                    progress = True
                    break
                if seg[-1] == ring[-1]:
                    ring.extend(list(reversed(seg))[1:])
                    remaining.pop(i)
                    progress = True
                    break
                if seg[-1] == ring[0]:
                    ring[0:0] = seg[:-1]
                    remaining.pop(i)
                    progress = True
                    break
                if seg[0] == ring[0]:
                    ring[0:0] = list(reversed(seg))[:-1]
                    remaining.pop(i)
                    progress = True
                    break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
        # 안 닫히면 버린다 — 이 relation 은 outer 조립 실패로 스킵.
    return rings


def _parse_relation(element: dict[str, object]) -> ParkPolygon | None:
    """relation(멀티폴리곤) 하나를 outer 멤버만 모아 조립한다."""
    members = element.get("members")
    if not isinstance(members, list):
        return None

    segments: list[list[Point]] = []
    for member in members:
        if member.get("type") != "way" or member.get("role") != "outer":
            continue
        geometry = member.get("geometry")
        if not isinstance(geometry, list) or len(geometry) < 2:
            continue
        segments.append([(point["lon"], point["lat"]) for point in geometry])

    rings = _stitch_rings(segments)
    if not rings:
        return None

    tags_raw = element.get("tags")
    tags: dict[str, object] = tags_raw if isinstance(tags_raw, dict) else {}
    if len(rings) == 1:
        geometry_out: dict[str, object] = {
            "type": "Polygon",
            "coordinates": [[list(point) for point in rings[0]]],
        }
    else:
        geometry_out = {
            "type": "MultiPolygon",
            "coordinates": [[[list(point) for point in ring]] for ring in rings],
        }
    name = tags.get("name")
    return ParkPolygon(geometry=geometry_out, name=name if isinstance(name, str) else None)


class OverpassParkSource:
    def __init__(self, client: OverpassClient) -> None:
        self._client = client

    def polygons_near(
        self, lat: float, lon: float, radius_m: float
    ) -> list[ParkPolygon]:
        south, west, north, east = _bbox(lat, lon, radius_m)
        bbox = f"{south},{west},{north},{east}"
        query = (
            "[out:json][timeout:25];"
            f'(way["leisure"~"^(park|garden)$"]({bbox});'
            f'way["landuse"="recreation_ground"]({bbox});'
            f'relation["leisure"~"^(park|garden)$"]({bbox}););'
            "out geom;"
        )
        raw = self._client.query(query)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OverpassFetchError(
                f"Overpass 응답이 JSON이 아니다 (길이 {len(raw)}자): {raw[:200]!r}"
            ) from exc

        remark = data.get("remark")
        if remark:
            # elements 가 비어 있어도 "0개 발견"이 아니라 쿼리 실패일 수 있다
            # (예: 서버 타임아웃) — 빈 리스트로 조용히 넘기지 않는다.
            raise OverpassFetchError(f"Overpass 쿼리 실패: {remark}")

        polygons: list[ParkPolygon] = []
        for element in data.get("elements", []):
            if element.get("type") == "relation":
                parsed = _parse_relation(element)
                if parsed is not None:
                    polygons.append(parsed)
                continue

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
