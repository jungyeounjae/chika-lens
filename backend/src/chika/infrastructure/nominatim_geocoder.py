"""`LandmarkGeocoder` 포트의 실제 구현 — Nominatim(OSM) 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. overpass_park_source.py 와
같은 구조 — 배치가 아니라 요청 한 건을 위해 Nominatim 을 실시간으로
호출한다.
"""

from __future__ import annotations

import json

from chika.domain.model.landmark import LandmarkMatch
from chika.etl.nominatim_client import NominatimClient, NominatimFetchError


class NominatimGeocoder:
    def __init__(self, client: NominatimClient) -> None:
        self._client = client

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        raw = self._client.search(query, limit)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NominatimFetchError(
                f"Nominatim 응답이 JSON이 아니다 (길이 {len(raw)}자): {raw[:200]!r}"
            ) from exc
        if not isinstance(data, list):
            raise NominatimFetchError(f"Nominatim 응답이 배열이 아니다: {raw[:200]!r}")

        matches: list[LandmarkMatch] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            lat_raw, lon_raw = item.get("lat"), item.get("lon")
            if lat_raw is None or lon_raw is None:
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                display_name = item.get("display_name")
                name = display_name.split(",")[0] if isinstance(display_name, str) else query
            matches.append(LandmarkMatch(name=name, lat=float(lat_raw), lon=float(lon_raw)))
        return matches
