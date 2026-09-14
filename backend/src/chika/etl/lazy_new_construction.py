"""구 단위 lazy 크롤링 — 챗봇이 처음 물어보는 구만 그 자리에서 크롤링+보강한다.

배치(`build_new_construction.py`/`build_new_construction_enrichment.py`)는
23구를 미리 다 돈다. 이 모듈은 반대다 — `search_new_construction`이 아직
크롤링 안 한 구를 물으면, 그 구 하나만 즉시 크롤링해서 캐시에 채워 넣는다.
23구를 전부 미리 긁을 필요가 없어지고, 실제로 질문받은 구만 데이터가 쌓인다.

개인 사적 이용 한정은 build_new_construction.py 와 동일 — 스펙 §2.3.1.

크롤링/보강 중 오류(네트워크, MLIT API, SUUMO 마크업 변경)가 나면 조용히
실패한다 — 채팅 턴 전체를 죽이면 안 되므로. "크롤링 완료" 기록은 실패 시
남기지 않아 다음 질문 때 재시도된다.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from chika.etl.build_new_construction import (
    _crawl_ward,
    _geocode_all,
    _load_geocode_cache,
    _to_dict,
)
from chika.etl.build_new_construction_enrichment import (
    DEFAULT_HAZARD_RADIUS_M,
    _load_ridership,
    _load_stations,
    enrich_listing,
)
from chika.etl.gsi_geocoder import GsiGeocoder
from chika.etl.mlit_client import MlitClient
from chika.etl.suumo_client import SuumoClient
from chika.etl.suumo_wards import TOKYO_23_WARDS
from chika.infrastructure.mlit_hazard_source import MlitHazardPolygonSource

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data")
_LISTINGS_PATH = _DATA_DIR / "new_construction.json"
_ENRICHED_PATH = _DATA_DIR / "new_construction_enriched.json"
_CRAWLED_WARDS_PATH = _DATA_DIR / "new_construction_crawled_wards.json"
_CACHE_DIR = _DATA_DIR / ".cache" / "suumo_new_construction"
_GEOCODE_CACHE_PATH = _DATA_DIR / ".cache" / "geocode_cache.json"
_STATIONS_PATH = _DATA_DIR / "stations.json"
_RIDERSHIP_PATH = _DATA_DIR / "mlit_ridership.json"


def ensure_ward_crawled(
    ward_ja: str, *, mlit_api_key: str, crawled_wards_path: Path = _CRAWLED_WARDS_PATH
) -> None:
    """`ward_ja`(예: "練馬区")가 아직 크롤링 안 됐으면 지금 크롤링+보강한다.

    이미 크롤링했거나 SUUMO 슬러그를 모르는 구면 아무것도 하지 않는다.
    `crawled_wards_path`는 테스트가 실제 `data/`를 건드리지 않고 캐시 히트
    동작을 확인할 수 있게 여는 파라미터다 — 실제 사용에선 기본값을 쓴다.
    """
    slug = TOKYO_23_WARDS.get(ward_ja)
    if slug is None:
        return

    crawled = _load_crawled_wards(crawled_wards_path)
    if slug in crawled:
        return

    try:
        _crawl_and_enrich_ward(ward_ja, slug, mlit_api_key)
    except Exception:
        logger.exception("lazy 크롤링 실패: %s (%s)", ward_ja, slug)
        return

    crawled[slug] = datetime.now(UTC).isoformat()
    _save_crawled_wards(crawled, crawled_wards_path)


def _crawl_and_enrich_ward(ward_ja: str, slug: str, mlit_api_key: str) -> None:
    client = SuumoClient()
    new_listings = _crawl_ward(client, ward_ja, slug, _CACHE_DIR, refresh=False)

    geocode_cache = _load_geocode_cache(_GEOCODE_CACHE_PATH)
    geocoded = _geocode_all(new_listings, GsiGeocoder(), geocode_cache)
    _GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GEOCODE_CACHE_PATH.write_text(
        json.dumps(geocode_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    new_raw = [_to_dict(item) for item in geocoded]
    merged_raw = _merge_by_suumo_id(_read_json_list(_LISTINGS_PATH), new_raw)
    _LISTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LISTINGS_PATH.write_text(
        json.dumps(merged_raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    hazard_source = MlitHazardPolygonSource(MlitClient(mlit_api_key))
    stations = _load_stations(_STATIONS_PATH)
    ridership = _load_ridership(_RIDERSHIP_PATH)
    enriched_new = [
        enrich_listing(row, hazard_source, stations, ridership, DEFAULT_HAZARD_RADIUS_M)
        for row in new_raw
    ]

    merged_enriched = _merge_by_suumo_id(_read_json_list(_ENRICHED_PATH), enriched_new)
    _ENRICHED_PATH.write_text(
        json.dumps(merged_enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _merge_by_suumo_id(
    existing: list[dict[str, object]], new: list[dict[str, object]]
) -> list[dict[str, object]]:
    by_id = {str(row["suumo_id"]): row for row in existing}
    for row in new:
        by_id[str(row["suumo_id"])] = row
    return list(by_id.values())


def _read_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    loaded: list[dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _load_crawled_wards(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _save_crawled_wards(crawled: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(crawled, ensure_ascii=False, indent=2), encoding="utf-8")
