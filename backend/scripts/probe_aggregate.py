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
import math
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
    ("nuisance_venue", ["storage", "car_repair", "car_wash", "truck_stop"], None),
]

#: 지표 10(음식점 다양성)의 요리 타입 바스켓.
#: 점수는 '몇 종류가 있나'가 아니라 '얼마나 고르게 분포하나'다 — 도쿄 역세권은
#: 대부분 8종이 전부 존재해 종 수로는 변별이 되지 않는다 (나카노 실측 8/8).
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


def effective_type_count(counts: list[int]) -> float:
    """섀넌 엔트로피의 유효 종 수 exp(H).

    '몇 종류가 있나'(존재 종 수)는 도쿄에서 거의 모든 역이 만점이라 변별이 안 된다.
    한 타입이 압도하면 1에 가깝고, 고르게 분포하면 타입 수에 가까워진다.
    """
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        share = count / total
        entropy -= share * math.log(share)
    return math.exp(entropy)


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
    counts: list[int] = []
    for cuisine in CUISINE_BASKET:
        result = compute_insights(key, [cuisine])
        calls += 1
        count = int(str(result.get("count", 0)))
        counts.append(count)
        print(f"  {cuisine:<26} {count:>4}")

    total = sum(counts)
    present = sum(1 for c in counts if c > 0)
    effective = effective_type_count(counts)
    print(f"\n  총 음식점 {total}")
    print(f"  존재 종 수      {present} / {len(CUISINE_BASKET)}  (포화되어 변별력 없음)")
    print(f"  유효 종 수      {effective:.2f} / {len(CUISINE_BASKET)}  <- 지표 10 값")
    if total:
        top = max(zip(CUISINE_BASKET, counts, strict=True), key=lambda kv: kv[1])
        print(f"  최다 타입       {top[0]} {100.0 * top[1] / total:.0f}%")
    return calls


#: 감점 상권 후보. 나카노 실측에서 묶음 합계가 382로 나와,
#: 어느 타입이 지배하는지 분해해 지표 15의 구성을 다시 정하기 위한 목록.
NUISANCE_CANDIDATES = [
    "storage",
    "car_repair",
    "car_wash",
    "truck_stop",
    "bar",
    "night_club",
    "casino",
    "liquor_store",
]


def run_nuisance(key: str) -> int:
    """지표 15의 구성 진단.

    묶음 합계만으로는 'bar가 압도해서 번화가 점수가 되어버린' 상황을
    구분할 수 없다. 타입별로 나눠 봐야 감점 지표로 쓸 수 있는지 판단이 선다.
    """
    print("=== 감점 상권 분해 — 나카노역 800m ===\n")
    print(f"{'타입':<20} {'count':>6}")
    print("-" * 30)
    counts: dict[str, int] = {}
    for candidate in NUISANCE_CANDIDATES:
        result = compute_insights(key, [candidate])
        count = int(str(result.get("count", 0)))
        counts[candidate] = count
        print(f"{candidate:<20} {count:>6}")

    total = sum(counts.values())
    print(f"\n  합계 {total}")
    if total:
        print("\n  구성비:")
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            share = 100.0 * count / total
            print(f"    {name:<20} {share:>5.1f}%")
    return len(NUISANCE_CANDIDATES)


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
    parser.add_argument("--nuisance", action="store_true", help="감점 상권 타입별 분해")
    args = parser.parse_args()

    if not (args.smoke or args.metrics or args.places or args.nuisance):
        parser.error("--smoke / --metrics / --places / --nuisance 중 하나 이상을 지정한다")

    key = _api_key()
    calls = 0
    if args.smoke:
        calls += run_smoke(key)
    if args.metrics:
        calls += run_metrics(key)
    if args.places:
        calls += run_places(key)
    if args.nuisance:
        calls += run_nuisance(key)

    print(f"\n>>> 이 실행이 사용한 computeInsights 호출: {calls}건")
    print(">>> GCP 청구서의 Places Aggregate API 요청 수와 대조하면 과금 단위를 알 수 있다.")


if __name__ == "__main__":
    main()
