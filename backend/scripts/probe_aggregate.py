"""Places Aggregate API 계약 검증 프로브.

스펙 §11의 미결 사항을 실측으로 닫기 위한 일회성 도구다.

  1. API 키가 살아 있고 areainsights.googleapis.com 이 활성화됐는가
  2. 응답 형태가 문서와 같은가 (count, placeInsights)
  3. 지표 13개의 타입 필터가 실제로 결과를 내는가
  4. 과금 단위 — 이 스크립트가 정확히 몇 콜을 쓰는지 출력하므로,
     실행 후 GCP 청구서와 대조하면 1콜=1요청인지 알 수 있다

사용법:

    export GOOGLE_MAPS_API_KEY=...        # 키를 인자로 넘기지 말 것 (셸 히스토리에 남는다)
    uv run python scripts/probe_aggregate.py --smoke     # 1콜만
    uv run python scripts/probe_aggregate.py --metrics   # 13콜, 지표별 타입 필터 검증
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://areainsights.googleapis.com/v1:computeInsights"

#: 나카노역. 도쿄 23구 안이면서 번화가와 주택가가 섞여 있어 프로브에 적당하다.
NAKANO = (35.7056, 139.6659)
RADIUS_M = 800

#: 스펙 §6.2의 Aggregate 조회 지표. (지표 키, includedTypes, minRating)
METRIC_QUERIES: list[tuple[str, list[str], float | None]] = [
    ("korean_restaurant", ["korean_restaurant"], 4.0),
    ("supermarket", ["supermarket"], None),
    ("convenience_store", ["convenience_store"], None),
    ("healthcare", ["pharmacy", "hospital", "doctor"], None),
    ("cafe", ["cafe"], 4.5),
    ("park", ["park"], None),
    ("fitness", ["gym"], 4.5),
    ("child_friendly_venue", ["playground", "amusement_park", "zoo", "aquarium"], None),
    ("nuisance_venue", ["storage", "car_repair", "bar", "night_club"], None),
]

#: 지표 10(음식점 다양성)의 요리 타입 바스켓 후보. count > 0 인 타입 수가 다양성 점수다.
CUISINE_BASKET = [
    "japanese_restaurant",
    "chinese_restaurant",
    "italian_restaurant",
    "indian_restaurant",
    "thai_restaurant",
    "fast_food_restaurant",
    "ramen_restaurant",
    "sushi_restaurant",
]


def _api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        sys.exit(
            "GOOGLE_MAPS_API_KEY 가 비어 있다.\n"
            "  export GOOGLE_MAPS_API_KEY=...   (키를 명령행 인자로 넘기지 말 것)"
        )
    return key


def compute_insights(
    key: str,
    included_types: list[str],
    min_rating: float | None = None,
    insight: str = "INSIGHT_COUNT",
) -> dict[str, object]:
    """computeInsights 1회. 호출 1건 = 이 함수 1번이다."""
    body: dict[str, object] = {
        "insights": [insight],
        "filter": {
            "locationFilter": {
                "circle": {
                    "latLng": {"latitude": NAKANO[0], "longitude": NAKANO[1]},
                    "radius": RADIUS_M,
                }
            },
            "typeFilter": {"includedTypes": included_types},
            "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
        },
    }
    if min_rating is not None:
        body["filter"]["ratingFilter"] = {"minRating": min_rating}  # type: ignore[index]

    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            parsed: dict[str, object] = json.loads(response.read().decode("utf-8"))
            return parsed
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        # 키가 본문에 실릴 일은 없지만, 혹시 모를 에코를 막는다.
        sys.exit(f"HTTP {exc.code}\n{detail.replace(key, '<REDACTED>')}")


def run_smoke(key: str) -> int:
    print("=== 스모크: 나카노역 800m 편의점 (1콜) ===")
    result = compute_insights(key, ["convenience_store"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


def run_metrics(key: str) -> int:
    calls = 0
    print(f"=== 지표별 타입 필터 검증 — 나카노역 반경 {RADIUS_M}m ===\n")
    print(f"{'지표':<24} {'count':>6}  타입")
    print("-" * 78)
    for name, types, min_rating in METRIC_QUERIES:
        result = compute_insights(key, types, min_rating)
        calls += 1
        count = result.get("count", "?")
        rating_note = f" (평점 {min_rating}+)" if min_rating else ""
        print(f"{name:<24} {count:>6}  {'+'.join(types)}{rating_note}")

    print(f"\n=== 음식점 다양성 바스켓 ({len(CUISINE_BASKET)}개 타입) ===")
    present = 0
    for cuisine in CUISINE_BASKET:
        result = compute_insights(key, [cuisine])
        calls += 1
        count = int(str(result.get("count", 0)))
        if count > 0:
            present += 1
        print(f"  {cuisine:<26} {count:>4}")
    print(f"\n  다양성 점수 = count>0 인 타입 수 = {present} / {len(CUISINE_BASKET)}")
    return calls


def run_places(key: str) -> int:
    """count <= 100 일 때 place ID가 실제로 오는지 확인한다.

    place ID는 캐싱 제한에서 면제되어 영구 보관할 수 있으므로,
    이게 되면 '이름을 알려면 Places API를 매번 불러야 한다'는 제약이 사라진다.
    """
    print("=== INSIGHT_PLACES: 나카노역 800m 한식당 (1콜) ===")
    result = compute_insights(key, ["korean_restaurant"], insight="INSIGHT_PLACES")
    insights = result.get("placeInsights", [])
    assert isinstance(insights, list)
    print(f"place ID {len(insights)}건")
    for item in insights[:5]:
        print(f"  {item}")
    if len(insights) > 5:
        print(f"  ... 외 {len(insights) - 5}건")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="1콜만 — 키와 API 활성화 확인")
    parser.add_argument("--metrics", action="store_true", help="지표별 타입 필터 검증")
    parser.add_argument("--places", action="store_true", help="INSIGHT_PLACES로 place ID 확인")
    args = parser.parse_args()

    if not (args.smoke or args.metrics or args.places):
        parser.error("--smoke / --metrics / --places 중 하나 이상을 지정한다")

    key = _api_key()
    calls = 0
    if args.smoke:
        calls += run_smoke(key)
    if args.metrics:
        calls += run_metrics(key)
    if args.places:
        calls += run_places(key)

    print(f"\n>>> 이 실행이 사용한 computeInsights 호출: {calls}건")
    print(">>> GCP 청구서의 Places Aggregate API 요청 수와 대조하면 과금 단위를 알 수 있다.")


if __name__ == "__main__":
    main()
