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
from pathlib import Path

from chika.etl.aggregate_batch import effective_type_count
from chika.etl.aggregate_queries import CORE_QUERIES, CUISINE_BASKET

ENDPOINT = "https://areainsights.googleapis.com/v1:computeInsights"

#: 배치와 같은 정의를 쓴다 — 검증한 것과 실행하는 것이 갈라지지 않게.
METRIC_QUERIES: list[tuple[str, list[str], float | None]] = [
    (q.key, list(q.included_types), q.min_rating) for q in CORE_QUERIES
]
CUISINE_BASKET_TYPES: list[str] = [q.included_types[0] for q in CUISINE_BASKET]

#: 나카노역. 도쿄 23구 안이면서 번화가와 주택가가 섞여 있어 프로브에 적당하다.
NAKANO = (35.7056, 139.6659)
RADIUS_M = 800




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
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, object]:
    """computeInsights 1회. 호출 1건 = 이 함수 1번이다 (2026-09-07 실측)."""
    center_lat = NAKANO[0] if lat is None else lat
    center_lon = NAKANO[1] if lon is None else lon
    body: dict[str, object] = {
        "insights": [insight],
        "filter": {
            "locationFilter": {
                "circle": {
                    "latLng": {"latitude": center_lat, "longitude": center_lon},
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

    print(f"\n=== 음식점 다양성 바스켓 ({len(CUISINE_BASKET_TYPES)}개 타입) ===")
    counts: list[int] = []
    for cuisine in CUISINE_BASKET_TYPES:
        result = compute_insights(key, [cuisine])
        calls += 1
        count = int(str(result.get("count", 0)))
        counts.append(count)
        print(f"  {cuisine:<26} {count:>4}")

    total = sum(counts)
    present = sum(1 for c in counts if c > 0)
    effective = effective_type_count(counts)
    print(f"\n  총 음식점 {total}")
    print(f"  존재 종 수      {present} / {len(CUISINE_BASKET_TYPES)}  (포화되어 변별력 없음)")
    print(f"  유효 종 수      {effective:.2f} / {len(CUISINE_BASKET_TYPES)}  <- 지표 10 값")
    if total:
        top = max(zip(CUISINE_BASKET_TYPES, counts, strict=True), key=lambda kv: kv[1])
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


def run_distribution(key: str, metric_names: list[str], sample_size: int) -> int:
    """실제 역 마스터에서 표본을 뽑아 지표의 변별력을 잰다.

    퍼센타일 정규화는 값이 서로 달라야 의미가 있다. 한 지표가 대부분의 역에서
    같은 값(특히 0~2 같은 좁은 범위)이면 순위가 동률로 뭉개져 지표가 죽는다.
    지표 구성을 확정하기 전에 이걸 확인해야, 어댑터를 다 만든 뒤에 스키마를
    다시 손보는 일을 피할 수 있다.
    """
    stations_path = Path("data/stations.json")
    if not stations_path.exists():
        sys.exit(f"역 마스터가 없다: {stations_path}")
    stations = json.loads(stations_path.read_text(encoding="utf-8"))

    # 결정적 등간격 표본. 역 마스터가 id 정렬이라 구·노선이 고루 섞인다.
    step = max(1, len(stations) // sample_size)
    sample = stations[::step][:sample_size]

    by_name = {name: (types, rating) for name, types, rating in METRIC_QUERIES}
    calls = 0
    for metric_name in metric_names:
        if metric_name not in by_name:
            sys.exit(f"알 수 없는 지표: {metric_name} (가능: {', '.join(by_name)})")
        types, min_rating = by_name[metric_name]

        print(f"\n=== {metric_name} — 표본 {len(sample)}역 ===")
        print(f"    {'+'.join(types)}" + (f" (평점 {min_rating}+)" if min_rating else ""))
        counts: list[tuple[str, int]] = []
        for station in sample:
            result = compute_insights(
                key, types, min_rating, lat=station["lat"], lon=station["lon"]
            )
            calls += 1
            counts.append((station["name_ja"], int(str(result.get("count", 0)))))

        values = sorted(c for _, c in counts)
        distinct = len(set(values))
        zeros = sum(1 for v in values if v == 0)
        mode_value = max(set(values), key=values.count)
        mode_share = 100.0 * values.count(mode_value) / len(values)
        median = values[len(values) // 2]

        for name, count in sorted(counts, key=lambda kv: -kv[1]):
            print(f"      {name:<12} {count:>5}")
        print(f"    최소 {values[0]}  중앙 {median}  최대 {values[-1]}")
        print(
            f"    고유값 {distinct}/{len(values)}  0인 역 {zeros}  "
            f"최빈값 {mode_value}({mode_share:.0f}%)"
        )
        verdict = (
            "변별력 낮음 — 지표 재검토" if distinct <= len(values) // 3 or mode_share >= 40
            else "변별력 충분"
        )
        print(f"    >>> {verdict}")
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
    parser.add_argument("--nuisance", action="store_true", help="감점 상권 타입별 분해")
    parser.add_argument(
        "--distribution", nargs="+", metavar="METRIC", help="지표 변별력 진단 (표본 조회)"
    )
    parser.add_argument("--sample", type=int, default=20, help="--distribution 표본 역 수")
    args = parser.parse_args()

    if not (args.smoke or args.metrics or args.places or args.nuisance or args.distribution):
        parser.error("--smoke / --metrics / --places / --nuisance / --distribution 중 하나 이상")

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
    if args.distribution:
        calls += run_distribution(key, args.distribution, args.sample)

    print(f"\n>>> 이 실행이 사용한 computeInsights 호출: {calls}건")
    print(">>> GCP 청구서의 Places Aggregate API 요청 수와 대조하면 과금 단위를 알 수 있다.")


if __name__ == "__main__":
    main()
