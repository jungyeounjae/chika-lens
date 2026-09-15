# 신축 물건 챗봇 툴 배선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `data/new_construction_enriched.json`(SUUMO 크롤러 + 재해/정숙도 결합 배치의 산출물)을 챗봇이 실제로 조회·설명할 수 있게 한다. "신주쿠구 신축 중에 안전한 곳 추천해줘", "예산 1억엔 이하 신축 알려줘", "이 신축 정숙한 편이야?", "이 물건 언제 입주해?" 같은 질문에 답할 수 있어야 한다.

**Architecture:** 기존 `rank_areas`/`explain_area` 쌍과 똑같은 3계층 구조를 그대로 따른다 — `domain/repository.py`에 새 포트(`NewConstructionRepository`), `infrastructure/`에 그 포트의 파일 기반 구현체(`FileNewConstructionRepository`, 실시간 크롤링 없이 배치 산출물만 읽는다), `application/usecase/`에 필터링 로직(`NewConstructionSearch`). 마지막으로 `interface/agent/`의 `actions.py`(로직)→`tools.py`(Agents SDK 어댑터)→`agents.py`(등록)→`prompts.py`(언제 쓸지) 4단 배선도 기존 `hazard_polygons`/`zoning_massing` 추가 때와 동일하다.

**"일반화" 설계 핵심:** 개별 질문(가격/면적/입주시기/안전성/정숙도)마다 툴을 따로 만들지 않는다. `search_new_construction`(검색+필터) 하나가 매물의 **전체 필드**(이름·주소·가격대·전용면적·인도시기·재해 요약·정숙도)를 그대로 돌려주고, LLM이 그 데이터를 보고 어떤 질문에도 자유롭게 답한다 — `explain_area`가 지표를 전부 던져주고 LLM이 알아서 서술하는 것과 같은 패턴이다. 필터 파라미터도 "안전한 곳만"/"조용한 곳만" 같은 이진 플래그가 아니라 `max_hazard_severity`/`min_daily_ridership` 같은 연속값으로 받는다 — LLM이 "꽤 안전한 곳"·"약간 번화한 곳" 같은 뉘앙스를 스스로 임계값으로 번역할 수 있게 한다.

**Tech Stack:** 기존 스택 그대로(Python 3.12, `openai-agents` SDK). 새 외부 의존성 없음 — `data/new_construction_enriched.json`을 읽기만 한다(실시간 크롤링/MLIT 호출 없음).

**Spec:** 사용자가 요청한 "신축 분양 물건 수집 + 안전성/정숙도 자동 결합을 챗봇에서 확인 가능하게" 기능. 시세 적정성 비교(신축 분양가 vs 주변 중고 시세)와 슈퍼마켓/편의점/P31 인프라는 각각 별도 계획(아직 미착수) — 이 계획은 이미 `new_construction_enriched.json`에 있는 필드만 노출한다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과, `mypy --strict` 통과.
- domain 계층은 `etl`을 몰라야 한다 — `etl/new_construction_hazard.py`의 `HazardSummary`, `etl/new_construction_quietness.py`의 `Quietness`를 domain에서 재사용하지 않는다. 대신 domain 전용의 동등한 값 객체(`HazardLevel`, `NewConstructionQuietness`)를 `domain/model/new_construction.py` 안에 새로 정의한다 — infrastructure 어댑터가 JSON dict를 이 domain 타입으로 변환한다.
- `UseCases`(`interface/agent/state.py`)는 `frozen=True` dataclass라 필드 하나를 추가하면 **모든 생성 지점**을 고쳐야 한다 — 정확히 5곳이다: `backend/src/chika/interface/cli.py:47`(`build_demo_session`), `cli.py:101`(`build_real_session`), `backend/tests/interface/test_agent_actions.py:107`, `:127`, `:1011`. 하나라도 빠뜨리면 그 파일의 다른 테스트가 `TypeError: missing argument`로 전부 깨진다.
- 결측 표현: `price_min_yen`/`price_max_yen`이 `None`이면 필터가 있을 때 그 물건은 제외한다(가격 미정 물건이 "예산 안"이라고 잘못 통과하면 안 된다) — 필터가 없으면(예: `search_new_construction()` 인자 없이 호출) 전부 포함한다. `hazard_summary`에 레이어가 없는 것과 `quietness.daily_ridership`가 `None`인 것은 각각 "그 레이어 데이터 없음"·"승하차인원 결측"이지 "안전함"/"0명"이 아니다 — 기존 `new_construction_hazard.py`/`new_construction_quietness.py`가 이미 지킨 구분을 여기서도 유지한다.
- `data/new_construction_enriched.json`이 없어도(아직 그 구를 크롤링/결합 배치를 안 돌림) 세션 생성 자체가 죽으면 안 된다 — `FileAreaMetricsRepository`의 필수 지표 파일과 달리, 신축 데이터는 원래 부분적이라 빈 리스트로 조용히 시작한다.

## 사전 조사 결과

- **기존 리스트형 툴 패턴(`rank_areas`)**: `interface/agent/tools.py:67-78`(스키마) → `interface/agent/actions.py:259-306`(`act_rank_areas`, 세션에 `state.last_ranking` 저장) → `application/usecase/rank_areas.py`(포트 조회+필터+정렬) → `interface/api/runner.py:41-78`이 SSE `tool` 이벤트로 `{tool, result}` 그대로 프론트에 흘려보낸다.
- **파일 기반 리포지토리 패턴**: `infrastructure/file_metrics.py`(`FileAreaMetricsRepository`) — `json.loads(path.read_text())`만 쓰고 라이브 API 호출 없음. 필수 파일 없으면 `FileNotFoundError`, 선택 파일 없으면 빈 dict(`_load_optional`). 이번 신축 리포지토리는 신축 데이터 자체가 선택적이라 **없으면 빈 리스트** 쪽을 따른다.
- **`UseCases`/`SessionState`**(`interface/agent/state.py:19-40`): `UseCases`는 툴 하나당 usecase 인스턴스 하나(frozen dataclass, 필드 전부 필수). `SessionState.last_ranking: list[RankedArea]`가 "직전 검색 결과를 두 번째 툴(`explain_area`류)이 참조"하는 기존 선례 — 이번에 `last_new_construction`을 똑같은 방식으로 추가한다.
- **`interface/cli.py`**: `build_demo_session`(line 42-57)과 `build_real_session`(line 60-111) 둘 다 `UseCases(...)`를 만든다. API 서버(`interface/api/app.py:121`)는 `build_real_session()`을 그대로 쓴다 — 여기 리포지토리 경로 인자를 추가하면 API에도 자동 반영된다.
- **`prompts.py`의 툴 분기 안내**: `ANALYSIS_INSTRUCTIONS`(89번째 줄~) 안에 `ward_price_ranking` 안내가 460-483줄에 있고, 그 바로 뒤(484줄)에 `metric_extremes` 안내가 이어진다 — 새 안내 문단을 483줄과 484줄 사이에 넣는다.

---

## Task 1: 도메인 모델 + 리포지토리 포트

**Files:**
- Create: `backend/src/chika/domain/model/new_construction.py`
- Modify: `backend/src/chika/domain/repository.py`
- Test: `backend/tests/domain/model/test_new_construction.py`

**Interfaces:**
- Produces: `HazardLevel(severity: float, label: str)`, `NewConstructionQuietness(station_id: str, station_name: str, distance_m: float, daily_ridership: float | None)`, `NewConstructionListing`(frozen dataclass, 13개 필드 — 아래 Step 3 참고), `NewConstructionRepository` Protocol(`listings() -> Sequence[NewConstructionListing]`). Task 2(infrastructure)·Task 3(usecase)·Task 4(agent)가 이 타입들을 그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/domain/model/test_new_construction.py
"""신축 물건 도메인 모델 — 필드 형태만 확인한다(순수 값 객체라 로직이 없다)."""

from __future__ import annotations

from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)


def test_a_listing_can_be_constructed_with_all_fields_present() -> None:
    listing = NewConstructionListing(
        suumo_id="67733465",
        name="リビオ高田馬場",
        ward="新宿区",
        address_raw="新宿区下落合１",
        lat=35.71574,
        lon=139.699585,
        price_min_yen=98_900_000,
        price_max_yen=172_900_000,
        floor_area_min_sqm=55.08,
        floor_area_max_sqm=76.56,
        delivery_period_raw="2027年4月下旬予定",
        url="https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/",
        fetched_at="2026-09-14",
        hazard_summary={"flood": HazardLevel(severity=0.667, label="5.0m~10.0m")},
        quietness=NewConstructionQuietness(
            station_id="st_844aa570351c",
            station_name="下落合",
            distance_m=387.8,
            daily_ridership=11361.0,
        ),
    )
    assert listing.hazard_summary["flood"].label == "5.0m~10.0m"
    assert listing.quietness is not None
    assert listing.quietness.daily_ridership == 11361.0


def test_a_listing_can_have_missing_coordinates_and_quietness() -> None:
    """지오코딩 결측·역 매칭 실패도 유효한 상태다 — None 허용."""
    listing = NewConstructionListing(
        suumo_id="1",
        name="테스트",
        ward="新宿区",
        address_raw="新宿区",
        lat=None,
        lon=None,
        price_min_yen=None,
        price_max_yen=None,
        floor_area_min_sqm=None,
        floor_area_max_sqm=None,
        delivery_period_raw="",
        url="",
        fetched_at="2026-09-14",
        hazard_summary={},
        quietness=None,
    )
    assert listing.lat is None
    assert listing.quietness is None
    assert listing.hazard_summary == {}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_new_construction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.new_construction'`

- [ ] **Step 3: `domain/model/new_construction.py` 구현**

```python
# backend/src/chika/domain/model/new_construction.py
"""신축 분양 물건 값 객체 — SUUMO 크롤러 + 재해/정숙도 결합 배치의 산출물을 담는다.

`etl/new_construction_hazard.py::HazardSummary`, `etl/new_construction_quietness.py::
Quietness`와 필드는 같지만 별개 타입이다 — domain은 etl을 몰라야 한다(Clean
Architecture, README "계층 규칙"). infrastructure 어댑터(FileNewConstructionRepository,
Task 2)가 JSON dict를 이 타입으로 변환한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HazardLevel:
    severity: float
    label: str


@dataclass(frozen=True)
class NewConstructionQuietness:
    station_id: str
    station_name: str
    distance_m: float
    #: 결측이면 None — 표본 부족 등으로 아직 계산 안 된 역일 수 있다. 0으로
    #: 채우지 않는다("한산한 역"과 "모르는 역"을 혼동하지 않기 위해).
    daily_ridership: float | None


@dataclass(frozen=True)
class NewConstructionListing:
    suumo_id: str
    name: str
    ward: str
    address_raw: str
    #: 지오코딩 결측이면 둘 다 None.
    lat: float | None
    lon: float | None
    price_min_yen: int | None
    price_max_yen: int | None
    floor_area_min_sqm: float | None
    floor_area_max_sqm: float | None
    delivery_period_raw: str
    url: str
    fetched_at: str
    #: 레이어별("flood"/"sediment"/"liquefaction"/"storm_surge"/"tsunami") 최고
    #: 위험도. 레이어가 없으면 그 레이어는 "데이터 없음"이지 "안전"이 아니다.
    hazard_summary: dict[str, HazardLevel]
    #: 최근접 역 매칭 실패(역 목록이 비어 있던 경우 등)면 None.
    quietness: NewConstructionQuietness | None
```

- [ ] **Step 4: `domain/repository.py`에 포트 추가**

`backend/src/chika/domain/repository.py`의 import 문에 `NewConstructionListing`을 추가하고, 파일 맨 끝에 새 Protocol을 추가한다:

```python
from chika.domain.model.new_construction import NewConstructionListing
```

(기존 import 블록의 `from chika.domain.model.polygon import ...` 아래 알파벳 순서에 맞게 넣는다.)

```python
class NewConstructionRepository(Protocol):
    """신축 분양 물건 조회 포트. 실시간 크롤링이 아니라 배치 산출물을 읽는다."""

    def listings(self) -> Sequence[NewConstructionListing]: ...
```

(`PriceRepository` class 뒤, 파일 맨 끝에 추가.)

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/domain/model/test_new_construction.py -v`
Expected: PASS (2 passed)

Run also: `cd backend && uv run pytest -q` (전체 스위트가 여전히 통과하는지 — `domain/repository.py` import 추가가 다른 곳을 깨지 않는지 확인. `NewConstructionRepository`를 아직 아무도 구현/소비하지 않으므로 새 실패는 없어야 한다.)

- [ ] **Step 6: 커밋**

```bash
git add backend/src/chika/domain/model/new_construction.py backend/src/chika/domain/repository.py backend/tests/domain/model/test_new_construction.py
git commit -m "feat(domain): 신축 물건 값 객체 + 리포지토리 포트 추가"
```

---

## Task 2: 파일 기반 리포지토리

**Files:**
- Create: `backend/src/chika/infrastructure/file_new_construction.py`
- Test: `backend/tests/infrastructure/test_file_new_construction.py`

**Interfaces:**
- Consumes: `NewConstructionListing`/`HazardLevel`/`NewConstructionQuietness`(Task 1).
- Produces: `FileNewConstructionRepository(path: Path)`, `.listings() -> Sequence[NewConstructionListing]`. Task 4가 이 클래스를 `cli.py`에서 인스턴스화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/infrastructure/test_file_new_construction.py
"""FileNewConstructionRepository — data/new_construction_enriched.json 형태 파싱."""

from __future__ import annotations

import json
from pathlib import Path

from chika.infrastructure.file_new_construction import FileNewConstructionRepository


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "new_construction_enriched.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def test_a_full_listing_is_parsed_with_hazard_and_quietness(tmp_path: Path) -> None:
    rows = [
        {
            "suumo_id": "67733465",
            "name": "リビオ高田馬場",
            "ward": "新宿区",
            "address_raw": "新宿区下落合１",
            "lat": 35.71574,
            "lon": 139.699585,
            "price_min_yen": 98_900_000,
            "price_max_yen": 172_900_000,
            "floor_area_min_sqm": 55.08,
            "floor_area_max_sqm": 76.56,
            "delivery_period_raw": "2027年4月下旬予定",
            "url": "https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/",
            "fetched_at": "2026-09-14",
            "hazard_summary": {
                "flood": {"severity": 0.6666666666666666, "label": "5.0m~10.0m"},
                "sediment": {"severity": 1.0, "label": "레드존(급경사지 붕괴위험, 지정완료)"},
            },
            "quietness": {
                "station_id": "st_844aa570351c",
                "station_name": "下落合",
                "distance_m": 387.8,
                "daily_ridership": 11361.0,
            },
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listings = repo.listings()

    assert len(listings) == 1
    listing = listings[0]
    assert listing.suumo_id == "67733465"
    assert listing.hazard_summary["flood"].label == "5.0m~10.0m"
    assert listing.hazard_summary["sediment"].severity == 1.0
    assert listing.quietness is not None
    assert listing.quietness.station_name == "下落合"
    assert listing.quietness.daily_ridership == 11361.0


def test_a_listing_with_no_coordinates_and_no_quietness_match(tmp_path: Path) -> None:
    rows = [
        {
            "suumo_id": "2",
            "name": "테스트",
            "ward": "新宿区",
            "address_raw": "新宿区",
            "lat": None,
            "lon": None,
            "price_min_yen": None,
            "price_max_yen": None,
            "floor_area_min_sqm": None,
            "floor_area_max_sqm": None,
            "delivery_period_raw": "",
            "url": "",
            "fetched_at": "2026-09-14",
            "hazard_summary": {},
            "quietness": None,
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listing = repo.listings()[0]

    assert listing.lat is None
    assert listing.quietness is None
    assert listing.hazard_summary == {}


def test_a_quietness_with_missing_ridership_stays_none(tmp_path: Path) -> None:
    """정숙도 매칭은 됐지만 승하차인원 자체가 결측인 경우(표본 부족 등)."""
    rows = [
        {
            "suumo_id": "3",
            "name": "테스트",
            "ward": "新宿区",
            "address_raw": "新宿区",
            "lat": 35.7,
            "lon": 139.7,
            "price_min_yen": None,
            "price_max_yen": None,
            "floor_area_min_sqm": None,
            "floor_area_max_sqm": None,
            "delivery_period_raw": "",
            "url": "",
            "fetched_at": "2026-09-14",
            "hazard_summary": {},
            "quietness": {
                "station_id": "st_x",
                "station_name": "テスト駅",
                "distance_m": 500.0,
                "daily_ridership": None,
            },
        }
    ]
    repo = FileNewConstructionRepository(_write(tmp_path, rows))

    listing = repo.listings()[0]

    assert listing.quietness is not None
    assert listing.quietness.daily_ridership is None


def test_a_missing_file_returns_an_empty_list_not_an_error(tmp_path: Path) -> None:
    """아직 그 구를 크롤링/결합 배치를 안 돌렸을 수 있다 — 세션이 죽으면 안 된다."""
    repo = FileNewConstructionRepository(tmp_path / "does_not_exist.json")

    assert repo.listings() == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/infrastructure/test_file_new_construction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.infrastructure.file_new_construction'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/infrastructure/file_new_construction.py
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

        return NewConstructionListing(
            suumo_id=str(row["suumo_id"]),
            name=str(row["name"]),
            ward=str(row["ward"]),
            address_raw=str(row["address_raw"]),
            lat=float(row["lat"]) if row.get("lat") is not None else None,
            lon=float(row["lon"]) if row.get("lon") is not None else None,
            price_min_yen=(
                int(row["price_min_yen"]) if row.get("price_min_yen") is not None else None
            ),
            price_max_yen=(
                int(row["price_max_yen"]) if row.get("price_max_yen") is not None else None
            ),
            floor_area_min_sqm=(
                float(row["floor_area_min_sqm"])
                if row.get("floor_area_min_sqm") is not None
                else None
            ),
            floor_area_max_sqm=(
                float(row["floor_area_max_sqm"])
                if row.get("floor_area_max_sqm") is not None
                else None
            ),
            delivery_period_raw=str(row["delivery_period_raw"]),
            url=str(row["url"]),
            fetched_at=str(row["fetched_at"]),
            hazard_summary=hazard_summary,
            quietness=quietness,
        )
```

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/infrastructure/test_file_new_construction.py -v` — 4 passed 기대.
Run: `cd backend && uv run ruff check src/chika/infrastructure/file_new_construction.py tests/infrastructure/test_file_new_construction.py && uv run mypy src/chika/infrastructure/file_new_construction.py` — 오류 없어야 한다.

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/infrastructure/file_new_construction.py backend/tests/infrastructure/test_file_new_construction.py
git commit -m "feat(infra): 신축 물건 파일 리포지토리 추가"
```

---

## Task 3: 검색 유스케이스 + 필터

**Files:**
- Create: `backend/src/chika/application/usecase/new_construction_search.py`
- Test: `backend/tests/application/test_new_construction_search.py`

**Interfaces:**
- Consumes: `NewConstructionRepository`(Task 1 포트), `NewConstructionListing`(Task 1).
- Produces: `NewConstructionFilter`(frozen dataclass, 6개 선택 필드), `NewConstructionSearch(repo: NewConstructionRepository)`, `.execute(filter: NewConstructionFilter, limit: int = 10) -> list[NewConstructionListing]`, `.find_by_id(suumo_id: str) -> NewConstructionListing | None`. Task 4가 이 클래스를 `UseCases`에 넣고 `actions.py`에서 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/application/test_new_construction_search.py
"""NewConstructionSearch — 구/가격대/재해위험/정숙도 필터 + find_by_id."""

from __future__ import annotations

from chika.application.usecase.new_construction_search import (
    NewConstructionFilter,
    NewConstructionSearch,
)
from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)


def _listing(
    suumo_id: str,
    ward: str = "新宿区",
    price_min_yen: int | None = 50_000_000,
    price_max_yen: int | None = 60_000_000,
    hazard_summary: dict[str, HazardLevel] | None = None,
    daily_ridership: float | None = 10_000.0,
) -> NewConstructionListing:
    return NewConstructionListing(
        suumo_id=suumo_id,
        name=f"物件{suumo_id}",
        ward=ward,
        address_raw="",
        lat=35.7,
        lon=139.7,
        price_min_yen=price_min_yen,
        price_max_yen=price_max_yen,
        floor_area_min_sqm=None,
        floor_area_max_sqm=None,
        delivery_period_raw="",
        url="",
        fetched_at="2026-09-14",
        hazard_summary=hazard_summary or {},
        quietness=NewConstructionQuietness(
            station_id="st_x", station_name="X", distance_m=300.0,
            daily_ridership=daily_ridership,
        ),
    )


class _FakeRepo:
    def __init__(self, listings: list[NewConstructionListing]) -> None:
        self._listings = listings

    def listings(self) -> list[NewConstructionListing]:
        return self._listings


def test_filters_by_ward() -> None:
    repo = _FakeRepo([_listing("1", ward="新宿区"), _listing("2", ward="渋谷区")])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(ward="渋谷区"))

    assert [item.suumo_id for item in result] == ["2"]


def test_excludes_listings_with_unknown_price_when_a_price_filter_is_active() -> None:
    repo = _FakeRepo(
        [
            _listing("1", price_min_yen=50_000_000, price_max_yen=60_000_000),
            _listing("2", price_min_yen=None, price_max_yen=None),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(max_price_yen=100_000_000))

    assert [item.suumo_id for item in result] == ["1"]


def test_no_price_filter_includes_listings_with_unknown_price() -> None:
    repo = _FakeRepo([_listing("1", price_min_yen=None, price_max_yen=None)])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter())

    assert [item.suumo_id for item in result] == ["1"]


def test_excludes_listings_whose_worst_hazard_severity_exceeds_the_threshold() -> None:
    repo = _FakeRepo(
        [
            _listing("safe", hazard_summary={"flood": HazardLevel(severity=0.2, label="x")}),
            _listing("risky", hazard_summary={"flood": HazardLevel(severity=0.9, label="y")}),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(max_hazard_severity=0.5))

    assert [item.suumo_id for item in result] == ["safe"]


def test_filters_by_ridership_range() -> None:
    repo = _FakeRepo(
        [
            _listing("quiet", daily_ridership=2_000.0),
            _listing("busy", daily_ridership=90_000.0),
        ]
    )
    search = NewConstructionSearch(repo)

    quiet_only = search.execute(NewConstructionFilter(max_daily_ridership=5_000.0))
    busy_only = search.execute(NewConstructionFilter(min_daily_ridership=50_000.0))

    assert [item.suumo_id for item in quiet_only] == ["quiet"]
    assert [item.suumo_id for item in busy_only] == ["busy"]


def test_results_are_sorted_by_price_ascending_with_unknown_price_last() -> None:
    repo = _FakeRepo(
        [
            _listing("expensive", price_min_yen=200_000_000),
            _listing("unknown", price_min_yen=None),
            _listing("cheap", price_min_yen=50_000_000),
        ]
    )
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter())

    assert [item.suumo_id for item in result] == ["cheap", "expensive", "unknown"]


def test_limit_caps_the_result_count() -> None:
    repo = _FakeRepo([_listing(str(i)) for i in range(5)])
    search = NewConstructionSearch(repo)

    result = search.execute(NewConstructionFilter(), limit=2)

    assert len(result) == 2


def test_find_by_id_returns_none_when_not_found() -> None:
    repo = _FakeRepo([_listing("1")])
    search = NewConstructionSearch(repo)

    assert search.find_by_id("does-not-exist") is None
    assert search.find_by_id("1") is not None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/application/test_new_construction_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.new_construction_search'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/application/usecase/new_construction_search.py
"""신축 물건 검색 — 구/가격대/재해위험/정숙도로 걸러 가격 오름차순 상위 N개.

개별 조건마다 툴을 만들지 않는다 — 이 하나의 필터 + 검색으로 "안전한 곳",
"조용한 곳", "예산 안" 같은 질문을 전부 표현한다. `max_hazard_severity`/
`min_daily_ridership`/`max_daily_ridership`는 연속값이라 LLM이 "꽤 안전한
곳"·"약간 번화한 곳" 같은 뉘앙스를 임계값으로 번역할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.new_construction import NewConstructionListing
from chika.domain.repository import NewConstructionRepository


@dataclass(frozen=True)
class NewConstructionFilter:
    ward: str | None = None
    max_price_yen: int | None = None
    min_price_yen: int | None = None
    #: 0~1, 클수록 위험. 이 값을 넘는 레이어가 하나라도 있으면 제외.
    max_hazard_severity: float | None = None
    #: 최근접 역의 일평균 승하차인원(정숙도 프록시) 범위.
    min_daily_ridership: float | None = None
    max_daily_ridership: float | None = None


class NewConstructionSearch:
    def __init__(self, repo: NewConstructionRepository) -> None:
        self._repo = repo

    def execute(
        self, filter: NewConstructionFilter, limit: int = 10
    ) -> list[NewConstructionListing]:
        matched = [
            listing for listing in self._repo.listings() if self._matches(listing, filter)
        ]
        matched.sort(key=self._sort_key)
        return matched[:limit]

    def find_by_id(self, suumo_id: str) -> NewConstructionListing | None:
        return next(
            (listing for listing in self._repo.listings() if listing.suumo_id == suumo_id),
            None,
        )

    @staticmethod
    def _sort_key(listing: NewConstructionListing) -> tuple[bool, int]:
        # 가격 미정(None)은 맨 뒤로 — 0으로 두면 "가장 싼 물건"으로 둔갑한다.
        return (listing.price_min_yen is None, listing.price_min_yen or 0)

    @staticmethod
    def _matches(listing: NewConstructionListing, filter: NewConstructionFilter) -> bool:
        if filter.ward is not None and listing.ward != filter.ward:
            return False

        if filter.max_price_yen is not None:
            if listing.price_min_yen is None or listing.price_min_yen > filter.max_price_yen:
                return False
        if filter.min_price_yen is not None:
            if listing.price_max_yen is None or listing.price_max_yen < filter.min_price_yen:
                return False

        if filter.max_hazard_severity is not None:
            if any(
                level.severity > filter.max_hazard_severity
                for level in listing.hazard_summary.values()
            ):
                return False

        if filter.min_daily_ridership is not None:
            ridership = listing.quietness.daily_ridership if listing.quietness else None
            if ridership is None or ridership < filter.min_daily_ridership:
                return False
        if filter.max_daily_ridership is not None:
            ridership = listing.quietness.daily_ridership if listing.quietness else None
            if ridership is not None and ridership > filter.max_daily_ridership:
                return False

        return True
```

- [ ] **Step 4: 테스트 통과 확인 + ruff/mypy**

Run: `cd backend && uv run pytest tests/application/test_new_construction_search.py -v` — 8 passed 기대.
Run: `cd backend && uv run ruff check src/chika/application/usecase/new_construction_search.py tests/application/test_new_construction_search.py && uv run mypy src/chika/application/usecase/new_construction_search.py`

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/application/usecase/new_construction_search.py backend/tests/application/test_new_construction_search.py
git commit -m "feat(application): 신축 물건 검색 유스케이스(구/가격/재해/정숙도 필터) 추가"
```

---

## Task 4: 에이전트 툴 배선 (actions/tools/agents/state/prompts/cli)

**Files:**
- Modify: `backend/src/chika/interface/agent/actions.py`
- Modify: `backend/src/chika/interface/agent/tools.py`
- Modify: `backend/src/chika/interface/agent/agents.py`
- Modify: `backend/src/chika/interface/agent/state.py`
- Modify: `backend/src/chika/interface/agent/prompts.py`
- Modify: `backend/src/chika/interface/cli.py`
- Modify: `backend/tests/interface/test_agent_actions.py`

**Interfaces:**
- Consumes: `NewConstructionSearch`/`NewConstructionFilter`(Task 3), `FileNewConstructionRepository`(Task 2), `NewConstructionListing`/`HazardLevel`/`NewConstructionQuietness`(Task 1).
- Produces: `act_search_new_construction`, `act_explain_new_construction`(actions.py) → `search_new_construction`, `explain_new_construction`(tools.py, `@function_tool`) → `AnalysisAgent`에 등록.

- [ ] **Step 1: `state.py` 수정**

```python
# backend/src/chika/interface/agent/state.py 전체 교체
"""대화 세션 상태. Agents SDK의 context로 전달된다 (스펙 §5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.hazard_polygons import HazardPolygons
from chika.application.usecase.metric_distribution import MetricDistribution
from chika.application.usecase.metric_extremes import MetricExtremes
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.application.usecase.rank_areas import RankAreas, RankedArea
from chika.application.usecase.ward_price import WardPriceRanking
from chika.application.usecase.zoning_massing import ZoningMassing
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.new_construction import NewConstructionListing


@dataclass(frozen=True)
class UseCases:
    rank: RankAreas
    explain: ExplainArea
    compare: CompareAreas
    distribution: MetricDistribution
    ward_price: WardPriceRanking
    extremes: MetricExtremes
    #: 원본 Polygon 3D 시각화용 — 배치가 아니라 요청 단위 실시간 MLIT 호출이다
    #: (hazard_polygons.py/zoning_massing.py 참고).
    hazard_polygons: HazardPolygons
    zoning_massing: ZoningMassing
    #: SUUMO 신축 분양 물건 검색 — 배치 산출물(new_construction_enriched.json)만
    #: 읽는다. 실시간 크롤링 없음.
    new_construction: NewConstructionSearch


@dataclass
class SessionState:
    usecases: UseCases
    criteria: SearchCriteria | None = None
    last_ranking: list[RankedArea] = field(default_factory=list)
    #: 직전 search_new_construction 결과 — explain_new_construction이 여기서
    #: 먼저 찾는다(rank_areas/explain_area가 last_ranking을 쓰는 것과 같은 패턴).
    last_new_construction: list[NewConstructionListing] = field(default_factory=list)
    #: LLM 대화 이력. 없으면 매 턴이 백지에서 시작해
    #: "공원은 몇개야?" 가 무엇에 대한 질문인지 알 수 없다 (스펙 §5.5).
    history: Any | None = None
```

- [ ] **Step 2: `actions.py`에 두 함수 추가**

파일 상단 import 블록에 추가(`from chika.application.usecase.rank_areas import RankedArea` 줄 근처, 알파벳 순서를 대략 지켜서):

```python
from chika.application.usecase.new_construction_search import NewConstructionFilter
from chika.domain.model.new_construction import (
    HazardLevel,
    NewConstructionListing,
    NewConstructionQuietness,
)
```

파일 맨 끝(`act_zoning_massing` 함수 뒤)에 추가:

```python
#: 한 번에 LLM에 넘기는 신축 물건 상한 — rank_areas의 MAX_RANKING_LIMIT과 같은 이유.
MAX_NEW_CONSTRUCTION_LIMIT = 10


def _hazard_summary_payload(hazard_summary: dict[str, HazardLevel]) -> dict[str, dict[str, Any]]:
    return {
        layer: {"severity": round(level.severity, 3), "label": level.label}
        for layer, level in hazard_summary.items()
    }


def _quietness_payload(quietness: NewConstructionQuietness | None) -> dict[str, Any] | None:
    if quietness is None:
        return None
    return {
        "station_id": quietness.station_id,
        "station_name": quietness.station_name,
        "distance_m": round(quietness.distance_m, 1),
        "daily_ridership": quietness.daily_ridership,
    }


def _new_construction_payload(listing: NewConstructionListing) -> dict[str, Any]:
    return {
        "suumo_id": listing.suumo_id,
        "name": listing.name,
        "ward": listing.ward,
        "address": listing.address_raw,
        "lat": listing.lat,
        "lon": listing.lon,
        "price_min_yen": listing.price_min_yen,
        "price_max_yen": listing.price_max_yen,
        "floor_area_min_sqm": listing.floor_area_min_sqm,
        "floor_area_max_sqm": listing.floor_area_max_sqm,
        "delivery_period": listing.delivery_period_raw,
        "url": listing.url,
        "fetched_at": listing.fetched_at,
        "hazard_summary": _hazard_summary_payload(listing.hazard_summary),
        "quietness": _quietness_payload(listing.quietness),
    }


def act_search_new_construction(
    state: SessionState,
    ward: str | None = None,
    max_price_yen: int | None = None,
    min_price_yen: int | None = None,
    max_hazard_severity: float | None = None,
    min_daily_ridership: float | None = None,
    max_daily_ridership: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    capped = max(1, min(limit, MAX_NEW_CONSTRUCTION_LIMIT))
    filter_ = NewConstructionFilter(
        ward=ward,
        max_price_yen=max_price_yen,
        min_price_yen=min_price_yen,
        max_hazard_severity=max_hazard_severity,
        min_daily_ridership=min_daily_ridership,
        max_daily_ridership=max_daily_ridership,
    )
    listings = state.usecases.new_construction.execute(filter_, limit=capped)
    state.last_new_construction = listings
    return {"listings": [_new_construction_payload(listing) for listing in listings]}


def act_explain_new_construction(state: SessionState, suumo_id: str) -> dict[str, Any]:
    listing = next(
        (item for item in state.last_new_construction if item.suumo_id == suumo_id), None
    )
    if listing is None:
        listing = state.usecases.new_construction.find_by_id(suumo_id)
    if listing is None:
        return {"error": "unknown_listing", "suumo_id": suumo_id}
    return _new_construction_payload(listing)
```

- [ ] **Step 3: `tools.py`에 두 툴 추가**

파일 맨 끝(`zoning_massing` 함수 뒤)에 추가:

```python
@function_tool
def search_new_construction(
    ctx: RunContextWrapper[SessionState],
    ward: str | None = None,
    max_price_yen: int | None = None,
    min_price_yen: int | None = None,
    max_hazard_severity: float | None = None,
    min_daily_ridership: float | None = None,
    max_daily_ridership: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """SUUMO에서 수집한 도쿄 23구 **신축 분양** 물건을 검색한다.

    `rank_areas`(역세권 랭킹, 489역 기존 데이터)와는 완전히 다른 데이터다 —
    "신축", "분양", "모델하우스" 관련 질문에 이 툴을 쓴다. `set_criteria`로
    조건을 확정할 필요 없이 바로 호출 가능하다.

    `ward`는 반드시 일본어 구 이름(예: "新宿区", "미나토구"가 아니다).
    `max_hazard_severity`(0~1, 낮을수록 안전)를 주면 그 값을 넘는 재해
    레이어가 하나라도 있는 물건을 제외한다 — "안전한 곳만"이면 0.5 정도를
    시작값으로 쓴다. `min_daily_ridership`/`max_daily_ridership`는 최근접
    역의 일평균 승하차인원(정숙도 프록시, 많을수록 번화가)으로 거른다 —
    "조용한 동네"면 max_daily_ridership를, "번화가"면 min_daily_ridership를
    쓴다. 가격은 전부 엔 단위(1억엔 = 100000000)다.

    결과는 세션에 저장되어, 이후 `explain_new_construction`으로 물건 하나를
    더 자세히 볼 수 있다. `hazard_summary`에 레이어가 없으면 "그 레이어
    데이터 없음"이지 "안전"이 아니다 — 답할 때 구분해서 말한다.
    """
    return actions.act_search_new_construction(
        ctx.context,
        ward=ward,
        max_price_yen=max_price_yen,
        min_price_yen=min_price_yen,
        max_hazard_severity=max_hazard_severity,
        min_daily_ridership=min_daily_ridership,
        max_daily_ridership=max_daily_ridership,
        limit=limit,
    )


@function_tool
def explain_new_construction(
    ctx: RunContextWrapper[SessionState], suumo_id: str
) -> dict[str, Any]:
    """신축 물건 하나의 전체 정보(가격·면적·인도시기·재해 요약·정숙도)를 낸다.

    `suumo_id`는 `search_new_construction` 결과에 있는 값을 그대로 쓴다.
    """
    return actions.act_explain_new_construction(ctx.context, suumo_id)
```

- [ ] **Step 4: `agents.py`에 등록**

`from chika.interface.agent.tools import (...)` 블록에 `explain_new_construction`, `search_new_construction`을 알파벳 순서로 추가하고, `AnalysisAgent`의 `tools=[...]` 리스트 끝에도 추가한다:

```python
from chika.interface.agent.tools import (
    compare_areas,
    explain_area,
    explain_new_construction,
    hazard_polygons,
    lookup_station,
    metric_distribution,
    metric_extremes,
    rank_areas,
    search_new_construction,
    set_criteria,
    ward_price_ranking,
    zoning_massing,
)


def build_agents() -> Agent[SessionState]:
    """진입 에이전트(IntakeAgent)를 반환한다. state는 Runner.run(context=...)로 넘긴다."""
    analysis: Agent[SessionState] = Agent(
        name="AnalysisAgent",
        instructions=ANALYSIS_INSTRUCTIONS,
        tools=[
            rank_areas,
            lookup_station,
            explain_area,
            compare_areas,
            metric_distribution,
            ward_price_ranking,
            metric_extremes,
            hazard_polygons,
            zoning_massing,
            search_new_construction,
            explain_new_construction,
        ],
    )
    ...
```

(`...` 이하 `intake`/`return` 블록은 그대로 둔다.)

- [ ] **Step 5: `prompts.py`에 안내 문단 추가**

`ANALYSIS_INSTRUCTIONS` 안에서 `- **시세 질문은 전부 ward_price_ranking.**` 문단(현재 460번째 줄 근처)이 끝나고 `- **비교 기준 없이 지표 하나만으로...` 문단(현재 484번째 줄 근처, `metric_extremes` 안내)이 시작되기 **직전**에 다음 문단을 새 bullet로 끼워 넣는다:

```
- **"신축", "분양", "모델하우스" 관련 질문은 search_new_construction /
  explain_new_construction.** `rank_areas`는 489개 기존 역세권을 다이얼로
  채점하는 것이고, 이 두 툴은 SUUMO에서 크롤링한 **신축 분양 중인 개별
  건물**을 다룬다 — 완전히 다른 데이터다. `set_criteria` 없이 바로
  호출한다.

  - "신주쿠구 신축 알려줘/추천해줘" → `search_new_construction(ward="新宿区")`.
    `ward`는 반드시 일본어(예: "新宿区"). 사용자가 "신주쿠구"라고 하면
    일본어로 변환해서 넘긴다.
  - "예산 1억엔 이하 신축" → `max_price_yen=100000000`. 물건의
    `price_min_yen`이 이 값보다 크면 제외된다 — `price_min_yen`이 아예
    없는(가격 미정) 물건도 필터가 걸리면 함께 제외된다(예산 안이라고
    확인할 수 없기 때문).
  - "안전한 신축만" → `max_hazard_severity=0.5` 정도로 시작한다(낮을수록
    엄격). 결과의 `hazard_summary`에 레이어가 없으면 "그 레이어는
    데이터가 확인되지 않았다"고 말하되 "안전하다"고 단정하지 않는다 —
    반경 안에 폴리곤이 없었다는 뜻이지, 별도로 안전성이 검증된 게
    아니다.
  - "조용한 동네 신축" → `max_daily_ridership`를 낮게(예: 10000). "역세권
    좋은/번화한 신축" → `min_daily_ridership`를 높게. `quietness`가
    `null`이면 최근접 역 매칭 자체가 안 된 것이다 — "정숙도 정보 없음"
    이라고 답하지 승하차인원을 0으로 지어내지 않는다.
  - 검색 결과에 나온 `suumo_id`로 `explain_new_construction`을 불러 물건
    하나를 더 자세히 설명한다 — 검색 없이 사용자가 곧바로 물건 하나를
    지목하면(예: 이전 답변에 있던 이름을 다시 언급) 그 답변에서 이미 본
    `suumo_id`를 그대로 쓴다.
  - `delivery_period`(인도시기)·`floor_area_min_sqm`/`floor_area_max_sqm`
    (전용면적)·`url`(원본 링크)도 그대로 있다 — 가격·안전성 얘기가 아니어도
    "언제 입주해?", "몇 평이야?" 같은 질문에 이 필드로 답한다.
```

- [ ] **Step 6: `cli.py` 수정**

파일 상단 import에 추가:

```python
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.infrastructure.file_new_construction import FileNewConstructionRepository
```

`build_demo_session`을 다음으로 교체(반환하는 `UseCases(...)`에 `new_construction` 필드 추가, 데모 세션이니 `data/new_construction_enriched.json`을 그대로 가리키게 한다 — 없으면 빈 리스트가 되므로 데모 자체는 깨지지 않는다):

```python
def build_demo_session(
    count: int = 40,
    new_construction_path: Path = Path("data/new_construction_enriched.json"),
) -> SessionState:
    stations, raws, commute, prices = build_seed(count=count)
    areas = FakeAreaMetricsRepository(stations, raws)
    client = _mlit_client()
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
            hazard_polygons=HazardPolygons(areas, MlitHazardPolygonSource(client)),
            zoning_massing=ZoningMassing(areas, MlitZoningPolygonSource(client)),
            new_construction=NewConstructionSearch(
                FileNewConstructionRepository(new_construction_path)
            ),
        )
    )
```

`build_real_session`의 함수 시그니처에 파라미터 추가(기존 `zoning_path` 파라미터 뒤):

```python
def build_real_session(
    stations_path: Path = Path("data/stations.json"),
    metrics_path: Path = Path("data/metrics.json"),
    ward_stats_path: Path = Path("data/ward_stats.json"),
    korean_shops_path: Path = Path("data/korean_shops.json"),
    childcare_path: Path = Path("data/mlit_childcare.json"),
    prices_path: Path = Path("data/mlit_prices.json"),
    hazards_path: Path = Path("data/mlit_hazards.json"),
    ridership_path: Path = Path("data/mlit_ridership.json"),
    zoning_path: Path = Path("data/mlit_zoning.json"),
    new_construction_path: Path = Path("data/new_construction_enriched.json"),
) -> SessionState:
```

그리고 함수 본문의 `UseCases(...)` 생성부에 마지막 필드로 추가:

```python
    areas = FileAreaMetricsRepository(
        stations_path,
        metrics_path,
        ward_stats_path,
        [
            korean_shops_path,
            childcare_path,
            prices_path,
            hazards_path,
            ridership_path,
            zoning_path,
        ],
    )
    client = _mlit_client()
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository({}), FakePriceRepository({})),
            explain=ExplainArea(areas, FakePriceRepository({})),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
            hazard_polygons=HazardPolygons(areas, MlitHazardPolygonSource(client)),
            zoning_massing=ZoningMassing(areas, MlitZoningPolygonSource(client)),
            new_construction=NewConstructionSearch(
                FileNewConstructionRepository(new_construction_path)
            ),
        )
    )
```

- [ ] **Step 7: 기존 테스트 3곳에 `new_construction` 필드 추가**

`backend/tests/interface/test_agent_actions.py`에서 `UseCases(` 생성이 3곳(107번째 줄, 127번째 줄, 1011번째 줄 근처)에 있다 — **각각의 `zoning_massing=...` 줄 바로 뒤에** 다음 한 줄을 추가한다(`frozen=True` dataclass라 필드 하나가 안 채워지면 그 생성 지점을 쓰는 테스트가 전부 `TypeError`로 깨진다):

```python
            new_construction=NewConstructionSearch(_FakeNewConstructionRepo([])),
```

이를 위해 파일 상단에 최소한의 페이크 리포지토리와 import를 추가한다(다른 `_Fake*` 클래스들 근처, 예를 들어 `_FakeZoningPolygonSource` 클래스 뒤):

```python
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.domain.model.new_construction import NewConstructionListing


class _FakeNewConstructionRepo:
    def __init__(self, listings: list[NewConstructionListing]) -> None:
        self._listings = listings

    def listings(self) -> list[NewConstructionListing]:
        return self._listings
```

- [ ] **Step 8: 새 액션 테스트 추가**

같은 파일(`test_agent_actions.py`) 맨 끝에 추가:

```python
# --- search_new_construction / explain_new_construction ---


def _new_construction_listing(suumo_id: str, ward: str = "新宿区") -> NewConstructionListing:
    from chika.domain.model.new_construction import HazardLevel, NewConstructionQuietness

    return NewConstructionListing(
        suumo_id=suumo_id,
        name=f"物件{suumo_id}",
        ward=ward,
        address_raw="新宿区下落合１",
        lat=35.71574,
        lon=139.699585,
        price_min_yen=98_900_000,
        price_max_yen=172_900_000,
        floor_area_min_sqm=55.08,
        floor_area_max_sqm=76.56,
        delivery_period_raw="2027年4月下旬予定",
        url="https://suumo.jp/x",
        fetched_at="2026-09-14",
        hazard_summary={"flood": HazardLevel(severity=0.5, label="0.5m~3.0m")},
        quietness=NewConstructionQuietness(
            station_id="st_x", station_name="下落合", distance_m=387.8, daily_ridership=11361.0
        ),
    )


def _state_with_new_construction(listings: list[NewConstructionListing]) -> SessionState:
    stations = [_station("a")]
    areas = FakeAreaMetricsRepository(stations, [_raw("a")])
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository({}), FakePriceRepository({})),
            explain=ExplainArea(areas, FakePriceRepository({})),
            compare=CompareAreas(areas),
            distribution=MetricDistribution(areas),
            ward_price=WardPriceRanking(areas),
            extremes=MetricExtremes(areas),
            hazard_polygons=HazardPolygons(areas, _FakeHazardPolygonSource()),
            zoning_massing=ZoningMassing(areas, _FakeZoningPolygonSource()),
            new_construction=NewConstructionSearch(_FakeNewConstructionRepo(listings)),
        )
    )


def test_search_new_construction_returns_listings_and_stores_them_in_session() -> None:
    session = _state_with_new_construction([_new_construction_listing("1")])

    result = act_search_new_construction(session, ward="新宿区")

    assert len(result["listings"]) == 1
    assert result["listings"][0]["suumo_id"] == "1"
    assert result["listings"][0]["hazard_summary"]["flood"]["label"] == "0.5m~3.0m"
    assert session.last_new_construction[0].suumo_id == "1"


def test_explain_new_construction_finds_a_listing_from_the_last_search() -> None:
    session = _state_with_new_construction([_new_construction_listing("1")])
    act_search_new_construction(session, ward="新宿区")

    result = act_explain_new_construction(session, "1")

    assert result["suumo_id"] == "1"
    assert result["quietness"]["station_name"] == "下落合"


def test_explain_new_construction_falls_back_to_the_repository_without_a_prior_search() -> None:
    session = _state_with_new_construction([_new_construction_listing("1")])

    result = act_explain_new_construction(session, "1")

    assert result["suumo_id"] == "1"


def test_explain_new_construction_reports_unknown_id() -> None:
    session = _state_with_new_construction([])

    result = act_explain_new_construction(session, "does-not-exist")

    assert result == {"error": "unknown_listing", "suumo_id": "does-not-exist"}
```

같은 파일 상단 import 블록에 `act_search_new_construction`, `act_explain_new_construction`도 추가한다(`from chika.interface.agent.actions import (...)` 블록, 알파벳 순서).

- [ ] **Step 9: 전체 스위트 + ruff/mypy 확인**

```bash
cd backend
uv run pytest -q
uv run ruff check src/chika/interface/ src/chika/application/usecase/new_construction_search.py tests/interface/
uv run mypy src/chika/interface/
```

전부 통과해야 한다. 기존 rank_areas/explain_area 등 다른 툴 테스트가 하나도 깨지지 않아야 한다 — `UseCases` 필드 추가로 인한 3곳의 누락이 없는지 이 실행이 확인해 준다.

- [ ] **Step 10: 커밋**

```bash
git add backend/src/chika/interface/agent/actions.py backend/src/chika/interface/agent/tools.py backend/src/chika/interface/agent/agents.py backend/src/chika/interface/agent/state.py backend/src/chika/interface/agent/prompts.py backend/src/chika/interface/cli.py backend/tests/interface/test_agent_actions.py
git commit -m "feat(agent): 신축 물건 검색/설명 툴을 AnalysisAgent에 배선"
```

---

## Task 5: 실제 실행으로 수동 검증

- [ ] **Step 1: 입력 데이터 준비**

이전 두 계획(SUUMO 크롤러, 공간 DB 결합)의 산출물이 로컬에 없으면 먼저 만든다:

```bash
cd backend
ls data/new_construction_enriched.json 2>/dev/null || {
  uv run python -m chika.etl.build_new_construction --wards shinjuku --refresh
  uv run python -m chika.etl.build_new_construction_enrichment
}
```

- [ ] **Step 2: CLI 데모로 배선 확인(OpenAI 키 불필요)**

`cli.py`의 `run_demo`는 `rank_areas`만 호출하므로 이걸로는 새 툴이 안 보인다 — 대신 액션 함수를 직접 스크립트로 호출해 배선이 실제로 맞물리는지 확인한다:

```bash
uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_search_new_construction, act_explain_new_construction

state = build_real_session()
result = act_search_new_construction(state, ward='新宿区', max_price_yen=200_000_000)
print(f'검색 결과 {len(result[\"listings\"])}건')
for item in result['listings'][:3]:
    print(f'  {item[\"name\"]} · {item[\"price_min_yen\"]}~{item[\"price_max_yen\"]}엔 · 재해 {list(item[\"hazard_summary\"].keys())} · 정숙도 {item[\"quietness\"]}')

if result['listings']:
    suumo_id = result['listings'][0]['suumo_id']
    detail = act_explain_new_construction(state, suumo_id)
    print(f'\\n단건 조회: {detail[\"name\"]} ({detail[\"delivery_period\"]})')
"
```

Expected: 신주쿠구 신축 물건이 가격 오름차순으로 나오고, 각 물건에 `hazard_summary`(레이어 있으면)·`quietness`(역 이름+거리+승하차인원)가 채워져 있어야 한다. 단건 조회도 같은 물건을 정확히 찾아야 한다.

- [ ] **Step 3: 필터 동작 확인**

```bash
uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_search_new_construction

state = build_real_session()
safe = act_search_new_construction(state, ward='新宿区', max_hazard_severity=0.3)
all_ = act_search_new_construction(state, ward='新宿区')
print(f'전체 {len(all_[\"listings\"])}건 중 안전 필터(0.3 이하) 통과 {len(safe[\"listings\"])}건')
"
```

Expected: 안전 필터를 걸면 전체보다 같거나 적은 건수가 나온다(0건이어도 에러가 아니다 — 신주쿠구 물건 전부가 그 임계값을 넘을 수 있다).

- [ ] **Step 4: 없는 구/빈 데이터 시 정상 동작 확인**

```bash
uv run python3 -c "
from chika.interface.cli import build_real_session
from chika.interface.agent.actions import act_search_new_construction

state = build_real_session()
result = act_search_new_construction(state, ward='存在しない区')
print(f'없는 구 조회: {len(result[\"listings\"])}건 (0건이어야 정상, 에러 아님)')
"
```

Expected: 예외 없이 `0건`. (이 계획은 "구 이름이 틀렸다"는 에러를 별도로 만들지 않는다 — 단순히 빈 결과를 낸다. 다른 구 이름 오류 처리가 필요하면 `ward_price_ranking`의 `unknown_ward` 패턴을 참고해 후속 개선하면 된다 — 이번 범위 밖.)

---

## Self-Review 체크리스트

- **스펙 커버리지**: "신축 분양 물건 수집 + 안전성/정숙도 자동 결합을 챗봇에서 확인 가능하게" — Task 1~5가 domain→infra→application→agent 전 계층을 배선해 구현한다. "신축의 정보에 대해서도 답변할 수 있도록 일반화" — `search_new_construction`/`explain_new_construction` 두 툴이 전체 필드를 그대로 반환해 LLM이 어떤 질문에도 답할 수 있게 했고, 필터도 이진 플래그가 아닌 연속값(가격/재해심각도/승하차인원)으로 노출해 특정 질문 패턴에 하드코딩되지 않았다.
- **플레이스홀더 스캔**: 모든 코드 블록이 실행 가능한 완성 코드다.
- **타입 일관성**: `NewConstructionListing`/`HazardLevel`/`NewConstructionQuietness`(Task 1 정의)가 Task 2(`FileNewConstructionRepository._parse`)·Task 3(`NewConstructionFilter`/`NewConstructionSearch`)·Task 4(`_new_construction_payload` 등)에서 필드명이 전부 일치한다. `UseCases`에 `new_construction` 필드를 추가하면서 생성 지점 5곳(cli.py 2곳, test_agent_actions.py 3곳)을 전부 짚었다.
- **아키텍처 경계**: domain은 etl을 모른다(`HazardLevel`/`NewConstructionQuietness`를 domain에 새로 정의, etl의 `HazardSummary`/`Quietness`를 재사용하지 않음). infrastructure만 shapely/JSON 같은 구체 의존을 알고, application은 포트(Protocol)만 안다 — 기존 `hazard_polygons`/`zoning_massing` 배선과 동일한 패턴.
- **프런트엔드**: 이번 계획 범위 밖이다. SSE 이벤트 계약(`{tool, result}`, `frontend/src/app/page.tsx`의 `event.tool === "..."` 분기)은 이미 확인했으니, 지도에 신축 물건 핀을 찍는 건 자연스러운 다음 단계로 남겨둔다 — 지금은 챗봇 텍스트 답변만 가능해진다.
