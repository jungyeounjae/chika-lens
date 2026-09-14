"""`NewConstructionRepository` 포트의 파일 기반 구현 — 배치 산출물만 읽는다.

`build_new_construction.py`(크롤링) + `build_new_construction_enrichment.py`
(재해·정숙도 결합)의 산출물(`data/new_construction_enriched.json`)을 읽기만
한다 — 여기서 크롤링이나 MLIT 실시간 호출을 하지 않는다.

`FileAreaMetricsRepository`(file_metrics.py)와 달리 파일이 없어도 예외를
던지지 않고 빈 리스트를 돌려준다 — 신축 데이터는 아직 크롤링 안 한 구가
있는 게 정상이라, 필수 지표 파일이 없는 것과 같은 수준의 오류가 아니다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)


class FileNewConstructionRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def listings(self) -> Sequence[NewConstructionListing]:
        if not self._path.exists():
            return []
        rows: list[dict[str, object]] = json.loads(self._path.read_text(encoding="utf-8"))
        return [self._parse(row) for row in rows]

    @staticmethod
    def _parse(row: dict[str, object]) -> NewConstructionListing:
        hazard_raw = row.get("hazard_summary") or {}
        assert isinstance(hazard_raw, dict)
        hazard_summary = {
            str(layer): HazardLevel(severity=float(value["severity"]), label=str(value["label"]))
            for layer, value in hazard_raw.items()
        }

        quietness_raw = row.get("quietness")
        quietness: NewConstructionQuietness | None = None
        if isinstance(quietness_raw, dict):
            ridership = quietness_raw.get("daily_ridership")
            quietness = NewConstructionQuietness(
                station_id=str(quietness_raw["station_id"]),
                station_name=str(quietness_raw["station_name"]),
                distance_m=float(quietness_raw["distance_m"]),
                daily_ridership=float(ridership) if ridership is not None else None,
            )

        lat = row.get("lat")
        lon = row.get("lon")
        price_min = row.get("price_min_yen")
        price_max = row.get("price_max_yen")
        floor_min = row.get("floor_area_min_sqm")
        floor_max = row.get("floor_area_max_sqm")

        return NewConstructionListing(
            suumo_id=str(row["suumo_id"]),
            name=str(row["name"]),
            ward=str(row["ward"]),
            address_raw=str(row["address_raw"]),
            lat=float(lat) if lat is not None else None,  # type: ignore[arg-type]
            lon=float(lon) if lon is not None else None,  # type: ignore[arg-type]
            price_min_yen=int(price_min) if price_min is not None else None,  # type: ignore[call-overload]
            price_max_yen=int(price_max) if price_max is not None else None,  # type: ignore[call-overload]
            floor_area_min_sqm=float(floor_min) if floor_min is not None else None,  # type: ignore[arg-type]
            floor_area_max_sqm=float(floor_max) if floor_max is not None else None,  # type: ignore[arg-type]
            delivery_period_raw=str(row["delivery_period_raw"]),
            url=str(row["url"]),
            fetched_at=str(row["fetched_at"]),
            hazard_summary=hazard_summary,
            quietness=quietness,
        )
