"""국토수치정보(N02 철도 / N03 행정구역) → 역 마스터.

다운로드는 수동이다. 연도별 파일명이 자주 바뀌어 URL을 코드에 박으면 금방 썩는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence

from chika.domain.model.station import Station

Ring = list[tuple[float, float]]
Ward = tuple[str, Ring]

TOKYO_PREFECTURE = "東京都"


def slugify_station(name_ja: str) -> str:
    """일본어 역명을 안정적인 ASCII id로 바꾼다.

    로마자 변환기를 의존성으로 들이는 대신 해시를 쓴다. id는 사람이 읽는 값이
    아니라 참조 키이고, 화면에는 name_ja가 나간다.
    """
    digest = hashlib.sha1(name_ja.encode("utf-8")).hexdigest()
    return f"st_{digest[:12]}"


def parse_ward_polygons(n03_geojson: Mapping[str, object]) -> list[Ward]:
    """도쿄도 시구정촌 폴리곤만 뽑는다. 멀티폴리곤은 링 단위로 펼친다."""
    wards: list[Ward] = []
    for feature in _features(n03_geojson):
        raw_props = feature.get("properties")
        props = raw_props if isinstance(raw_props, dict) else {}
        if props.get("N03_001") != TOKYO_PREFECTURE:
            continue
        name = props.get("N03_004")
        if not isinstance(name, str):
            continue
        raw_geometry = feature.get("geometry")
        geometry = raw_geometry if isinstance(raw_geometry, dict) else {}
        for ring in _outer_rings(geometry):
            wards.append((name, ring))
    return wards


def parse_stations(
    n02_geojson: Mapping[str, object],
    wards: Sequence[Ward],
) -> list[Station]:
    """N02 역 피처를 역명 기준으로 병합해 Station 목록을 만든다.

    같은 역명이 노선 수만큼 반복되므로 첫 좌표를 대표로 쓰고 노선만 합친다.
    """
    merged: dict[str, dict[str, object]] = {}

    for feature in _features(n02_geojson):
        raw_props = feature.get("properties")
        props = raw_props if isinstance(raw_props, dict) else {}
        name = props.get("N02_005")
        line = props.get("N02_003")
        if not isinstance(name, str) or not isinstance(line, str):
            continue

        raw_geometry = feature.get("geometry")
        geometry = raw_geometry if isinstance(raw_geometry, dict) else {}
        point = _representative_point(geometry)
        if point is None:
            continue
        lon, lat = point

        ward = _ward_containing(lon, lat, wards)
        if ward is None:
            continue  # 23구 밖

        station_id = slugify_station(name)
        entry = merged.setdefault(
            station_id,
            {"name_ja": name, "ward": ward, "lat": lat, "lon": lon, "lines": []},
        )
        lines = entry["lines"]
        assert isinstance(lines, list)
        if line not in lines:
            lines.append(line)

    stations: list[Station] = []
    for station_id, entry in merged.items():
        entry_lines = entry["lines"]
        assert isinstance(entry_lines, list)
        entry_lat = entry["lat"]
        entry_lon = entry["lon"]
        assert isinstance(entry_lat, float)
        assert isinstance(entry_lon, float)
        stations.append(
            Station(
                id=station_id,
                name_ja=str(entry["name_ja"]),
                    ward=str(entry["ward"]),
                lat=entry_lat,
                lon=entry_lon,
                lines=tuple(sorted(entry_lines)),
            )
        )
    return sorted(stations, key=lambda s: s.id)


def _features(geojson: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    features = geojson.get("features")
    if not isinstance(features, list):
        return []
    return [f for f in features if isinstance(f, dict)]


def _outer_rings(geometry: Mapping[str, object]) -> list[Ring]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon" and isinstance(coords, list) and coords:
        return [[(float(p[0]), float(p[1])) for p in coords[0]]]
    if kind == "MultiPolygon" and isinstance(coords, list):
        return [
            [(float(p[0]), float(p[1])) for p in polygon[0]] for polygon in coords if polygon
        ]
    return []


def _representative_point(geometry: Mapping[str, object]) -> tuple[float, float] | None:
    """N02 역은 LineString(플랫폼 선)이다. 중점을 역 좌표로 삼는다."""
    coords = geometry.get("coordinates")
    kind = geometry.get("type")
    if kind == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    if kind == "LineString" and isinstance(coords, list) and coords:
        lons = [float(p[0]) for p in coords]
        lats = [float(p[1]) for p in coords]
        return sum(lons) / len(lons), sum(lats) / len(lats)
    return None


def _ward_containing(lon: float, lat: float, wards: Sequence[Ward]) -> str | None:
    for name, ring in wards:
        if _point_in_ring(lon, lat, ring):
            return name
    return None


def _point_in_ring(lon: float, lat: float, ring: Ring) -> bool:
    """ray casting. 구 경계 판정에는 이걸로 충분하다."""
    inside = False
    count = len(ring)
    for i in range(count):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % count]
        if (y1 > lat) != (y2 > lat):
            x_at_lat = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_at_lat:
                inside = not inside
    return inside
