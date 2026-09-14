"""`SchoolFacilitySource` 포트의 실제 구현 — MLIT 실시간 조회.

domain/application 은 이 파일의 존재를 모른다. mlit_hazard_source.py 와 같은
구조다 — 배치가 아니라 요청 한 건을 위해 MLIT 을 실시간으로 호출한다(호출
과금 없음). 파싱은 etl.mlit_childcare 의 기존 함수를 그대로 재사용한다.
"""

from __future__ import annotations

from chika.domain.model.facility import SchoolFacility
from chika.domain.service.geo import distance_meters
from chika.etl.mlit_childcare import deduplicate, parse_preschool, parse_school
from chika.etl.mlit_client import MlitClient, tiles_covering
from chika.etl.mlit_datasets import PRESCHOOL, SCHOOL


class MlitSchoolFacilitySource:
    def __init__(self, client: MlitClient) -> None:
        self._client = client

    def facilities_near(self, lat: float, lon: float, radius_m: float) -> list[SchoolFacility]:
        preschool_raw: list[dict[str, object]] = []
        school_raw: list[dict[str, object]] = []
        for dataset, sink in ((PRESCHOOL, preschool_raw), (SCHOOL, school_raw)):
            for x, y in tiles_covering([(lat, lon)], dataset.zoom, radius_m):
                sink.extend(self._client.features(dataset, x, y))

        preschools = deduplicate(f for item in preschool_raw if (f := parse_preschool(item)))
        schools = deduplicate(f for item in school_raw if (f := parse_school(item)))

        result: list[SchoolFacility] = []
        for facility in [*preschools, *schools]:
            distance = distance_meters(lat, lon, facility.lat, facility.lon)
            if distance > radius_m:
                continue
            result.append(
                SchoolFacility(
                    facility_id=facility.facility_id,
                    name=facility.name,
                    kind=facility.kind,
                    lat=facility.lat,
                    lon=facility.lon,
                    distance_m=round(distance, 1),
                )
            )
        result.sort(key=lambda f: f.distance_m)
        return result
