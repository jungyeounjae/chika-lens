"""신축 물건 공간 DB 결합 배치 — 재해 안전성(MLIT) + 정숙도(역세권 승하차인원).

새 HTTP 클라이언트도, 새 MLIT 데이터셋도 없다 — 기존 MlitHazardPolygonSource
(재해)와 이미 배치로 계산된 mlit_ridership.json(정숙도)을 그대로 재사용한다.
슈퍼마켓·편의점·대형 집객시설(P31) 주변 인프라는 이번 배치 범위 밖이다 —
MLIT에 해당 데이터셋이 없고 Google Places Aggregate(호출당 과금)로만 조회
가능해서, 신축 물건 수만큼 유료 호출이 느는 걸 피하려고 별도 계획으로 미뤘다.

재해 조회 반경은 800m(역세권 단위, 기존 hazard_polygons usecase의 기본값)가
아니라 300m를 쓴다 — 역 상권 전체가 아니라 건물 하나의 재해 노출을 보는
것이므로 의도적으로 더 좁힌다.

MlitHazardPolygonSource는 요청 한 건짜리 실시간 조회를 위한 것이라 타일
캐시가 없다 — 이 배치처럼 물건 하나하나를 순회하며 부르면, 가까운 물건들이
겹치는 타일을 매번 다시 받아온다. 지금 규모(구별 수십 건)에서는 무해하지만,
나중에 여러 구를 한 번에 도는 배치로 커지면 공유 타일 캐시가 필요해진다.

사용법:

    export MLIT_API_KEY=...
    uv run python -m chika.etl.build_new_construction_enrichment
    uv run python -m chika.etl.build_new_construction_enrichment --radius-m 500
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from chika.domain.model.station import Station
from chika.etl.mlit_client import MlitApiError, MlitClient
from chika.etl.mlit_hazards import HazardShapeError
from chika.etl.new_construction_hazard import HazardSummary, summarize_hazards
from chika.etl.new_construction_quietness import Quietness, nearest_quietness
from chika.infrastructure.mlit_hazard_source import MlitHazardPolygonSource

#: 건물 단위 재해 노출 반경. 역세권 단위(800m, hazard_polygons usecase 기본값)
#: 보다 의도적으로 좁다 — 참고: 사전 조사 결과 절 및 Global Constraints.
DEFAULT_HAZARD_RADIUS_M = 300.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listings", type=Path, default=Path("data/new_construction.json")
    )
    parser.add_argument("--stations", type=Path, default=Path("data/stations.json"))
    parser.add_argument(
        "--ridership", type=Path, default=Path("data/mlit_ridership.json")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/new_construction_enriched.json")
    )
    parser.add_argument("--radius-m", type=float, default=DEFAULT_HAZARD_RADIUS_M)
    args = parser.parse_args()

    listings = json.loads(args.listings.read_text(encoding="utf-8"))
    stations = _load_stations(args.stations)
    ridership = _load_ridership(args.ridership)

    hazard_source = MlitHazardPolygonSource(MlitClient(_api_key()))

    enriched: list[dict[str, object]] = []
    skipped_no_coords = 0
    try:
        for index, listing in enumerate(listings, start=1):
            if index % 5 == 0 or index == len(listings):
                print(f"  {index}/{len(listings)}건 처리 중")

            lat, lon = listing.get("lat"), listing.get("lon")
            if lat is None or lon is None:
                skipped_no_coords += 1
                enriched.append({**listing, "hazard_summary": {}, "quietness": None})
                continue

            try:
                polygons = hazard_source.polygons_near(
                    float(lat), float(lon), args.radius_m
                )
            except HazardShapeError as exc:
                print(
                    f"    경고: {listing.get('name', '?')} 재해 조회 중 알 수 없는 "
                    f"값, 이 물건은 재해 결측으로 남긴다: {exc}"
                )
                polygons = []
            hazards = summarize_hazards(polygons)
            quietness = nearest_quietness(float(lat), float(lon), stations, ridership)

            enriched.append(
                {
                    **listing,
                    "hazard_summary": {
                        layer: _hazard_to_dict(summary)
                        for layer, summary in hazards.items()
                    },
                    "quietness": _quietness_to_dict(quietness) if quietness else None,
                }
            )
    except (MlitApiError, KeyboardInterrupt) as exc:
        sys.exit(f"중단: {exc}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"{len(enriched)}건 처리 ({skipped_no_coords}건은 좌표 없음, "
        f"재해 조회 반경 {args.radius_m:.0f}m) -> {args.out}"
    )


def _load_stations(path: Path) -> list[Station]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Station(
            id=row["id"],
            name_ja=row["name_ja"],
            ward=row["ward"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            lines=tuple(row["lines"]),
        )
        for row in rows
    ]


def _load_ridership(path: Path) -> dict[str, float]:
    raw: dict[str, dict[str, float]] = json.loads(path.read_text(encoding="utf-8"))
    return {station_id: values["daily_ridership"] for station_id, values in raw.items()}


def _hazard_to_dict(summary: HazardSummary) -> dict[str, object]:
    return {"severity": summary.severity, "label": summary.label}


def _quietness_to_dict(quietness: Quietness) -> dict[str, object]:
    return {
        "station_id": quietness.station_id,
        "station_name": quietness.station_name,
        "distance_m": round(quietness.distance_m, 1),
        "daily_ridership": quietness.daily_ridership,
    }


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. backend/.env 에 넣고 load-env.sh 를 쓴다.")
    return key


if __name__ == "__main__":
    main()
