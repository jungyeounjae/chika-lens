# 신축 물건 공간 DB 결합(재해 안전성 + 정숙도) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `data/new_construction.json`(SUUMO 신축 크롤러 산출물, [2026-09-14-suumo-new-construction-ingestion.md](2026-09-14-suumo-new-construction-ingestion.md)에서 구현)의 각 물건 좌표에 (1) MLIT 재해 레이어 기반 안전성 요약과 (2) 최근접 역의 승하차 인원(정숙도 프록시)을 자동으로 붙여 `data/new_construction_enriched.json`으로 낸다.

**Architecture:** 재해 안전성은 **완전히 기존 인프라를 재사용**한다 — `MlitHazardPolygonSource.polygons_near(lat, lon, radius_m)`(`backend/src/chika/infrastructure/mlit_hazard_source.py`)가 이미 임의의 좌표에 대해 5개 재해 레이어(홍수·토사·액상화·고조·쓰나미)를 실시간 조회하는 포트/구현체를 갖추고 있다 — 새 HTTP 클라이언트나 새 MLIT 데이터셋이 필요 없다. 정숙도도 새로 만들지 않는다 — 이미 배치로 계산돼 있는 역별 `daily_ridership`(`data/mlit_ridership.json`, `MetricKey.DAILY_RIDERSHIP`)을 최근접 역 매칭으로 재사용한다. 이번 계획이 실제로 새로 만드는 것은 순수 함수 두 개(재해 목록 → 층별 요약, 좌표 → 최근접 역+승하차인원)와 그걸 엮는 배치 스크립트 하나뿐이다.

이전 계획([2026-09-14-suumo-new-construction-ingestion.md](2026-09-14-suumo-new-construction-ingestion.md))과 같은 이유로 domain/application 계층은 건드리지 않는다 — 아직 application/interface가 신축 데이터를 소비하지 않는 순수 ETL 산출물이라, `build_prices.py`가 `Transaction`을 domain이 아니라 `etl/` 안에 두는 선례를 그대로 따른다.

**Tech Stack:** Python 3.12, 기존 `MlitClient`/`MlitHazardPolygonSource`(신규 코드 없음), `domain/service/geo.py::distance_meters`(기존, 외부 의존 0), pytest.

**Spec:** 사용자가 제시한 "신축 공급 추적 에이전트" 구상의 2번("기존 공간 DB와의 자동 결합") 중 **재해 안전성 자동 평가**와 **역세권 정숙도(승하차 인원)**만 범위로 한다. **슈퍼마켓·편의점·대형 집객시설(P31) 주변 인프라는 사용자 결정으로 이번 범위에서 제외** — 이 항목들은 MLIT에 데이터셋이 없고 이 저장소에서는 Google Places Aggregate API(호출당 과금)로만 조회 가능한데, 신축 물건 좌표마다 신규 유료 호출이 발생하므로 별도 계획으로 미룬다. 재개발 고시 파싱, 시세 적정성 엔진, 에이전트 UI도 각각 별도 계획이다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과 (`select = ["E", "F", "I", "UP", "B", "TID"]`), `mypy --strict` 통과.
- 신규 파일은 `backend/src/chika/etl/` 아래, 테스트는 `backend/tests/etl/` 아래.
- domain 타입(`HazardPolygon`, `Station`)을 etl에서 import하는 것은 기존 컨벤션과 일치한다(`build_prices.py`가 이미 `chika.domain.model.station.Station`을, `mlit_prices.py`가 `chika.domain.service.geo`를 가져다 쓴다) — 반대 방향(domain이 etl을 아는 것)만 금지.
- 재해 조회는 **건물 단위** 반경을 쓴다 — 기존 `hazard_polygons` usecase의 800m(역세권 단위)와 다른 값이다. 이 계획은 300m를 기본값으로 한다(건물 하나의 재해 노출을 보는 것이지 역 상권 전체를 보는 게 아니므로, 참고: `HazardPolygons.execute`의 기존 기본값은 800m — 의도적으로 다르게 간다).
- 재해 레이어가 반경 안에서 하나도 안 잡히면 "안전"이 아니라 "해당 레이어 데이터 없음(결측)"으로 남긴다 — `mlit_prices.py::MIN_SAMPLES`, `test_mlit_hazard_source.py`의 "빈 응답도 유효한 답" 철학과 같다.

## 사전 조사 결과

- `HazardPolygonSource` 포트(`backend/src/chika/domain/repository.py:20-24`): `polygons_near(self, lat: float, lon: float, radius_m: float) -> Sequence[HazardPolygon]`.
- `HazardPolygon`(`backend/src/chika/domain/model/polygon.py:14-19`): `layer: str`(`"flood"|"sediment"|"liquefaction"|"storm_surge"|"tsunami"`), `geometry: dict`, `severity: float`(0~1, 클수록 위험), `label: str`.
- `MlitHazardPolygonSource.polygons_near`(`backend/src/chika/infrastructure/mlit_hazard_source.py:104-143`)가 이미 구현체다 — 그대로 쓴다.
- 정숙도 소스: `data/mlit_ridership.json`은 `{station_id: {"daily_ridership": float}}` 형태(실측), `data/stations.json`은 `[{id, name_ja, ward, lat, lon, lines}]`(실측). `Station`(`backend/src/chika/domain/model/station.py:14-20`) 필드와 정확히 대응.
- `distance_meters(lat1, lon1, lat2, lon2) -> float`(`backend/src/chika/domain/service/geo.py:15`) — 하버사인, 외부 의존 0.
- `NewConstructionListing`(`backend/src/chika/etl/suumo_new_construction.py`): 이번 계획이 소비하는 입력. `lat`/`lon`이 `None`인 레코드(지오코딩 결측)는 건너뛴다.
- `build_prices.py`의 `_api_key()`(`MLIT_API_KEY` 환경변수 읽기) 패턴을 그대로 재사용한다.

---

## Task 1: 재해 목록 → 층별 안전성 요약 (순수 함수)

**Files:**
- Create: `backend/src/chika/etl/new_construction_hazard.py`
- Test: `backend/tests/etl/test_new_construction_hazard.py`

**Interfaces:**
- Consumes: `HazardPolygon`(`chika.domain.model.polygon`, 기존).
- Produces: `HazardSummary`(frozen dataclass: `layer: str`, `severity: float`, `label: str`), `summarize_hazards(polygons: Sequence[HazardPolygon]) -> dict[str, HazardSummary]` — key는 `layer`. Task 3이 이 dict를 JSON 직렬화해서 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_new_construction_hazard.py
"""HazardPolygon 목록 -> 층별(최고 위험도) 안전성 요약."""

from __future__ import annotations

from chika.domain.model.polygon import HazardPolygon
from chika.etl.new_construction_hazard import summarize_hazards


def _hazard(layer: str, severity: float, label: str) -> HazardPolygon:
    return HazardPolygon(layer=layer, geometry={}, severity=severity, label=label)


def test_a_single_layer_with_one_polygon_is_summarized_as_is() -> None:
    summary = summarize_hazards([_hazard("flood", 0.5, "3.0m~5.0m")])
    assert summary["flood"].severity == 0.5
    assert summary["flood"].label == "3.0m~5.0m"


def test_multiple_polygons_in_the_same_layer_keep_the_worst_severity() -> None:
    """반경 안에 같은 레이어 폴리곤이 여러 개 걸리면(경계 근처) 가장 위험한 것을
    대표값으로 삼는다 — 평균을 내면 위험이 희석되어 보인다."""
    summary = summarize_hazards(
        [
            _hazard("sediment", 0.4, "옐로존(지정완료)"),
            _hazard("sediment", 1.0, "레드존(지정완료)"),
        ]
    )
    assert summary["sediment"].severity == 1.0
    assert summary["sediment"].label == "레드존(지정완료)"


def test_layers_with_no_polygon_are_absent_not_zero() -> None:
    """반경 안에 해당 레이어가 하나도 안 잡히면 '안전(0)'이 아니라 '결측'이다 —
    키 자체가 없어야 호출부가 '이 레이어는 데이터가 없다'를 구분할 수 있다."""
    summary = summarize_hazards([_hazard("flood", 0.2, "0m~0.5m")])
    assert "tsunami" not in summary
    assert "liquefaction" not in summary


def test_an_empty_polygon_list_is_an_empty_summary() -> None:
    assert summarize_hazards([]) == {}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_new_construction_hazard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.new_construction_hazard'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/new_construction_hazard.py
"""HazardPolygon 목록(한 좌표 주변 조회 결과) -> 레이어별 최고 위험도 요약.

MlitHazardPolygonSource.polygons_near()가 반환하는 원본 목록은 반경 안에 걸린
폴리곤 전부를 담고 있어(경계 근처에서는 같은 레이어가 여러 개 걸릴 수 있다),
그대로 저장하면 "이 물건이 안전한가"를 한눈에 읽을 수 없다. 레이어마다 가장
위험한 값 하나로 접는다 — 평균을 내면 위험이 희석되어 보인다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.polygon import HazardPolygon


@dataclass(frozen=True)
class HazardSummary:
    layer: str
    severity: float
    label: str


def summarize_hazards(polygons: Sequence[HazardPolygon]) -> dict[str, HazardSummary]:
    """레이어별로 severity가 가장 큰(=가장 위험한) 폴리곤 하나만 남긴다.
    반경 안에 레이어가 하나도 안 잡히면 그 레이어의 키 자체가 없다 — '안전'과
    '데이터 없음'을 헷갈리지 않기 위해서다."""
    best: dict[str, HazardSummary] = {}
    for polygon in polygons:
        current = best.get(polygon.layer)
        if current is None or polygon.severity > current.severity:
            best[polygon.layer] = HazardSummary(
                layer=polygon.layer, severity=polygon.severity, label=polygon.label
            )
    return best
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_new_construction_hazard.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/new_construction_hazard.py backend/tests/etl/test_new_construction_hazard.py
git commit -m "feat(etl): 재해 폴리곤 목록을 레이어별 최고 위험도로 요약"
```

---

## Task 2: 좌표 → 최근접 역 + 승하차인원(정숙도) (순수 함수)

**Files:**
- Create: `backend/src/chika/etl/new_construction_quietness.py`
- Test: `backend/tests/etl/test_new_construction_quietness.py`

**Interfaces:**
- Consumes: `Station`(`chika.domain.model.station`, 기존), `distance_meters`(`chika.domain.service.geo`, 기존).
- Produces: `Quietness`(frozen dataclass: `station_id: str`, `station_name: str`, `distance_m: float`, `daily_ridership: float | None`), `nearest_quietness(lat: float, lon: float, stations: Sequence[Station], ridership: Mapping[str, float]) -> Quietness | None`(역 목록이 비어 있으면 `None`). Task 3이 이 결과를 JSON 직렬화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_new_construction_quietness.py
"""좌표 -> 최근접 역 + 그 역의 승하차인원(정숙도 프록시)."""

from __future__ import annotations

from chika.domain.model.station import Station
from chika.etl.new_construction_quietness import nearest_quietness

_SHINJUKU = Station(
    id="st_shinjuku", name_ja="新宿", ward="新宿区", lat=35.6896, lon=139.7006, lines=("JR山手線",)
)
_TAKADANOBABA = Station(
    id="st_takada", name_ja="高田馬場", ward="新宿区", lat=35.7127, lon=139.7038, lines=("JR山手線",)
)


def test_the_nearer_station_by_straight_line_distance_wins() -> None:
    # 신주쿠역과 거의 같은 좌표 -> 신주쿠가 최근접.
    result = nearest_quietness(
        35.6897, 139.7007, [_SHINJUKU, _TAKADANOBABA], {"st_shinjuku": 500_000.0}
    )
    assert result is not None
    assert result.station_id == "st_shinjuku"
    assert result.station_name == "新宿"
    assert result.distance_m < 100
    assert result.daily_ridership == 500_000.0


def test_a_station_missing_from_the_ridership_index_reports_missing_not_zero() -> None:
    """배치가 아직 안 돈 역이나 표본 부족으로 결측인 역이 있을 수 있다(스펙
    §MIN_SAMPLES) — 0으로 채우면 '한산한 역'과 '모르는 역'을 혼동한다."""
    result = nearest_quietness(35.6897, 139.7007, [_SHINJUKU], {})
    assert result is not None
    assert result.daily_ridership is None


def test_no_stations_at_all_returns_none() -> None:
    assert nearest_quietness(35.6897, 139.7007, [], {}) is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_new_construction_quietness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.new_construction_quietness'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/new_construction_quietness.py
"""신축 물건 좌표 -> 최근접 역 + 그 역의 일평균 승하차인원(정숙도 프록시).

정숙도 자체를 새로 계산하지 않는다 — 이미 배치로 계산된 역별
daily_ridership(build_ridership.py, MetricKey.DAILY_RIDERSHIP)을 재사용한다.
승하차인원이 많을수록 시끄러운 역세권이라는 게 이 지표의 기존 해석이다
(AreaMap.tsx의 DIRECTIONLESS_METRICS 참고 — "많다/적다"이지 "좋다/나쁘다"가
아니므로, 이 값을 '조용함' 점수로 뒤집는 건 이 모듈의 소비자 몫이다).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from chika.domain.model.station import Station
from chika.domain.service.geo import distance_meters


@dataclass(frozen=True)
class Quietness:
    station_id: str
    station_name: str
    distance_m: float
    #: 결측이면 None — 표본 부족(MIN_SAMPLES)으로 아직 계산 안 된 역일 수 있다.
    daily_ridership: float | None


def nearest_quietness(
    lat: float,
    lon: float,
    stations: Sequence[Station],
    ridership: Mapping[str, float],
) -> Quietness | None:
    """역 목록이 비어 있으면 None. 최근접 역의 승하차인원이 ridership 인덱스에
    없으면(결측) daily_ridership을 None으로 — 0으로 채우지 않는다."""
    if not stations:
        return None
    nearest = min(stations, key=lambda s: distance_meters(lat, lon, s.lat, s.lon))
    distance = distance_meters(lat, lon, nearest.lat, nearest.lon)
    return Quietness(
        station_id=nearest.id,
        station_name=nearest.name_ja,
        distance_m=distance,
        daily_ridership=ridership.get(nearest.id),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_new_construction_quietness.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/new_construction_quietness.py backend/tests/etl/test_new_construction_quietness.py
git commit -m "feat(etl): 신축 물건 좌표에 최근접 역+승하차인원 매칭 추가"
```

---

## Task 3: 배치 스크립트 조립 (`build_new_construction_enrichment.py`)

**Files:**
- Create: `backend/src/chika/etl/build_new_construction_enrichment.py`

**Interfaces:**
- Consumes: `summarize_hazards`/`HazardSummary`(Task 1), `nearest_quietness`/`Quietness`(Task 2), `MlitHazardPolygonSource`(기존, `chika.infrastructure.mlit_hazard_source`), `MlitClient`(기존, `chika.etl.mlit_client`), `Station`(기존).
- Produces: `data/new_construction_enriched.json` 파일. `build_prices.py`와 같은 이유로 이 CLI 파일 자체에는 전용 테스트를 붙이지 않는다 — 순수 로직은 Task 1·2에서 이미 테스트됐고, 이 파일은 그것들을 엮어 파일 I/O만 한다.

- [ ] **Step 1: 구현**

```python
# backend/src/chika/etl/build_new_construction_enrichment.py
"""신축 물건 공간 DB 결합 배치 — 재해 안전성(MLIT) + 정숙도(역세권 승하차인원).

새 HTTP 클라이언트도, 새 MLIT 데이터셋도 없다 — 기존 MlitHazardPolygonSource
(재해)와 이미 배치로 계산된 mlit_ridership.json(정숙도)을 그대로 재사용한다.
슈퍼마켓·편의점·대형 집객시설(P31) 주변 인프라는 이번 배치 범위 밖이다 —
MLIT에 해당 데이터셋이 없고 Google Places Aggregate(호출당 과금)로만 조회
가능해서, 신축 물건 수만큼 유료 호출이 느는 걸 피하려고 별도 계획으로 미뤘다.

재해 조회 반경은 800m(역세권 단위, 기존 hazard_polygons usecase의 기본값)가
아니라 300m를 쓴다 — 역 상권 전체가 아니라 건물 하나의 재해 노출을 보는
것이므로 의도적으로 더 좁힌다.

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
    for listing in listings:
        lat, lon = listing.get("lat"), listing.get("lon")
        if lat is None or lon is None:
            skipped_no_coords += 1
            enriched.append({**listing, "hazard_summary": {}, "quietness": None})
            continue

        try:
            polygons = hazard_source.polygons_near(float(lat), float(lon), args.radius_m)
        except MlitApiError as exc:
            sys.exit(f"중단: {exc}")
        hazards = summarize_hazards(polygons)
        quietness = nearest_quietness(float(lat), float(lon), stations, ridership)

        enriched.append(
            {
                **listing,
                "hazard_summary": {
                    layer: _hazard_to_dict(summary) for layer, summary in hazards.items()
                },
                "quietness": _quietness_to_dict(quietness) if quietness else None,
            }
        )

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
```

- [ ] **Step 2: mypy/ruff 통과 확인**

Run: `cd backend && uv run ruff check src/chika/etl/build_new_construction_enrichment.py && uv run mypy src/chika/etl/build_new_construction_enrichment.py`
Expected: 오류 없음

- [ ] **Step 3: 커밋**

```bash
git add backend/src/chika/etl/build_new_construction_enrichment.py
git commit -m "feat(etl): 신축 물건 재해 안전성+정숙도 결합 배치 스크립트 추가"
```

---

## Task 4: 실제 실행으로 수동 검증

배치 CLI 자체는 전용 단위 테스트가 없으므로(Task 3 참고), 이전 계획에서 만든 신주쿠구 23건 데이터로 실제 실행해 산출물을 눈으로 확인한다.

- [ ] **Step 1: 입력 데이터 준비 확인**

이전 계획(SUUMO 크롤러)의 산출물 `data/new_construction.json`은 로컬 생성 파일이라 커밋되지 않는다. 없으면 먼저 만든다:

```bash
cd backend && ls data/new_construction.json 2>/dev/null || \
  uv run python -m chika.etl.build_new_construction --wards shinjuku --refresh
```

- [ ] **Step 2: 결합 배치 실행**

```bash
uv run python -m chika.etl.build_new_construction_enrichment
```

Expected 출력 예: `23건 처리 (0건은 좌표 없음, 재해 조회 반경 300m) -> data/new_construction_enriched.json` 근처의 값.

- [ ] **Step 3: 산출물 확인**

```bash
cat data/new_construction_enriched.json | python3 -m json.tool | head -50
```

각 물건에 원래 필드(`name`, `address_raw`, `lat`, `lon` 등)가 그대로 있고, 추가로:
- `hazard_summary`: 레이어별(`flood`/`sediment`/`liquefaction`/`storm_surge`/`tsunami`) `{severity, label}` — 신주쿠는 저지대라 최소 하나는 채워질 가능성이 높다. 전부 빈 dict인 물건이 있으면 그 좌표를 직접 https://www.reinfolib.mlit.go.jp 에서 확인하거나, 반경(300m) 안에 정말 재해 레이어가 없는지 판단한다.
- `quietness`: `{station_id, station_name, distance_m, daily_ridership}` — `station_name`이 실제로 신주쿠구 인근 역인지, `distance_m`이 상식적인 범위(보통 수백 m)인지 확인한다.

- [ ] **Step 4: 결측 케이스 확인**

```bash
python3 -c "
import json
data = json.load(open('data/new_construction_enriched.json'))
no_hazard = [d['name'] for d in data if not d['hazard_summary']]
no_ridership = [d['name'] for d in data if d['quietness'] and d['quietness']['daily_ridership'] is None]
print(f'재해 레이어 전무: {len(no_hazard)}건', no_hazard[:5])
print(f'정숙도(승하차인원) 결측: {len(no_ridership)}건', no_ridership[:5])
"
```

결측이 전부는 아닌지(=배치가 통째로 실패해 전원 결측으로 나온 게 아닌지) 확인한다. 일부만 결측이면 정상 — 신축 물건 전부가 재해 레이어에 걸리거나 승하차인원이 잡히는 건 아니다.

---

## Self-Review 체크리스트

- **스펙 커버리지**: 사용자가 승인한 범위(재해 안전성 + 정숙도)를 Task 1~4가 구현한다. 슈퍼마켓·편의점·P31은 사용자가 명시적으로 이번 범위에서 제외했음 — Goal/Spec 절에 기록됨.
- **플레이스홀더 스캔**: 모든 코드 블록이 실행 가능한 완성 코드다.
- **타입 일관성**: `HazardSummary`/`Quietness` 필드명이 Task 1·2(정의)와 Task 3(`_hazard_to_dict`/`_quietness_to_dict`)에서 동일. `MlitHazardPolygonSource.polygons_near`/`Station`/`distance_meters` 시그니처는 기존 코드 그대로라 별도 정의 없음.
- **재사용 확인**: 새 HTTP 클라이언트·새 MLIT 데이터셋·새 도메인 타입 없음 — 전부 기존 인프라(`MlitHazardPolygonSource`, `mlit_ridership.json`) 재사용. 이 계획이 실제로 추가하는 코드는 순수 함수 2개 + 그걸 엮는 배치 1개뿐.
