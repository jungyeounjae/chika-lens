"""`ZoningPolygonSource` 포트의 실제 구현 — MLIT 실시간 조회 + shapely 거리 계산.

`mlit_hazard_source.py`와 같은 이유로 shapely·MlitClient 의존을 여기 안에
가둔다.
"""

from __future__ import annotations

from shapely.geometry import shape

from chika.domain.model.polygon import ZoningPolygon
from chika.etl.mlit_client import MlitClient, tiles_covering
from chika.etl.mlit_datasets import ZONING
from chika.etl.mlit_hazards import nearest_distance_m

#: 용도지역별 압출 높이(m) — 실제 법정 높이 제한(용적률·높이지구 등은 지자체
#: 조례마다 다르다)이 아니라, "저층 vs 고밀"을 눈으로 가르기 위한 일러스트용
#: 임의 배율이다. 1・2=저층, 3・4=중고층, 5~7=주거지역, 8=준주거,
#: 9・10=근린상업・상업(가장 높게), 11・12=준공업・공업.
# ponytail: 지자체별 실제 높이지구를 반영하려면 별도 데이터가 필요하다 —
# 지금은 시각적 대비용 근사치일 뿐이다.
HEIGHT_BY_YOUTO_ID: dict[int, float] = {
    1: 10.0,
    2: 10.0,
    3: 20.0,
    4: 20.0,
    5: 31.0,
    6: 31.0,
    7: 31.0,
    8: 31.0,
    9: 45.0,
    10: 60.0,
    11: 31.0,
    12: 31.0,
}
_DEFAULT_HEIGHT_M = 20.0


class MlitZoningPolygonSource:
    def __init__(self, client: MlitClient) -> None:
        self._client = client

    def polygons_near(self, lat: float, lon: float, radius_m: float) -> list[ZoningPolygon]:
        tiles = tiles_covering([(lat, lon)], ZONING.zoom, radius_m)
        seen_ids: set[str] = set()
        polygons: list[ZoningPolygon] = []
        for x, y in tiles:
            for feature in self._client.features(ZONING, x, y):
                properties = feature.get("properties")
                if not isinstance(properties, dict):
                    continue
                feature_id = str(properties.get("_id", ""))
                if feature_id and feature_id in seen_ids:
                    continue
                youto_id = properties.get("youto_id")
                if not isinstance(youto_id, int):
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
                    ZoningPolygon(
                        geometry=geometry_dict,
                        youto_id=youto_id,
                        use_area_ja=str(properties.get("use_area_ja", "")),
                        height_m=HEIGHT_BY_YOUTO_ID.get(youto_id, _DEFAULT_HEIGHT_M),
                    )
                )
        return polygons
