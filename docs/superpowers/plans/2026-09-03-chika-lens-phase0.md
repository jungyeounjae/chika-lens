# Chika Lens Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 외부 데이터 승인(Places Insights / MLIT) 없이, 순수 도메인 로직과 Fake 리포지토리만으로 "대화 → 조건 수집 → 역세권 랭킹 → 근거 설명"이 끝까지 동작하는 백엔드를 완성한다.

**Architecture:** 클린 아키텍처 4계층. `domain`은 표준 라이브러리만 쓰는 순수 파이썬(pydantic조차 금지)이고, 스코어링·정규화가 여기에 산다. `application`은 리포지토리 **포트**(Protocol)에만 의존하는 유스케이스. `infrastructure`는 Phase 0에서 Fake 구현만 제공하며, Phase 1~2에서 BigQuery/MLIT 어댑터로 교체된다. `interface`는 OpenAI Agents SDK 어댑터로, 툴 함수는 유스케이스를 호출만 한다.

**Tech Stack:** Python 3.12, uv, pytest, ruff, mypy, openai-agents SDK, pydantic(=interface 계층 전용), shapely+pyproj(ETL 전용)

**Spec:** [docs/superpowers/specs/2026-09-03-chika-lens-design.md](../specs/2026-09-03-chika-lens-design.md)

## Global Constraints

- Python **3.12** 고정 (`requires-python = ">=3.12,<3.13"`). `uv python pin 3.12`.
- 패키지 루트는 `backend/src/chika`, src-layout. 모든 테스트는 `backend/`에서 `uv run pytest` 로 실행한다.
- **`chika.domain` 은 표준 라이브러리 외 어떤 것도 import 하지 않는다.** pydantic·openai·google-cloud 모두 금지. 이 규칙은 Task 12의 자동 테스트로 강제한다.
- `chika.application` 은 `chika.domain` 만 import 한다. `chika.infrastructure` / `chika.interface` 를 import 하면 위반.
- 지표 키는 **15개 고정**이며 `MetricKey` StrEnum 이 유일한 정의처다. 문자열 리터럴로 지표를 참조하지 않는다.
- 다이얼은 **5개 고정**(`Dial` StrEnum). LLM은 다이얼 5개의 상대 강도만 정하고, 15개 가중치는 도메인이 펼친다.
- 점수는 항상 `50 + Σ w_k · (percentile_k − 50)` 이며 **LLM은 어떤 수치도 계산하지 않는다**.
- 결측 지표는 퍼센타일 50을 넣되 반드시 `missing` 플래그에 남긴다. 조용히 채우지 않는다.
- 감점 지표(`PRICE_LEVEL`, `DISASTER_RISK`, `NUISANCE_VENUE`)는 정규화 단계에서 `100 − percentile` 로 뒤집어, 이후 전 계층에서 "높을수록 좋음"으로 통일한다.
- 커밋 메시지는 Conventional Commits (`feat:`, `test:`, `chore:`, `docs:`).
- 어떤 태스크도 실제 네트워크 호출을 테스트에 포함하지 않는다.

### 스펙 대비 의도적 구체화 2건

1. 스펙 §5.2의 `SearchCriteria` 는 `weights: Weights` 를 들고 있고 pydantic `BaseModel` 이다. 본 계획에서는 **도메인 순수성 제약** 때문에 `SearchCriteria` 를 stdlib dataclass 로 두고 `dials: DialSettings` 를 들게 한다(가중치는 §6.4대로 도메인이 펼친다). LLM 구조화 출력용 pydantic 모델은 `interface/agent/` 에만 둔다.
2. 스펙의 `hard_filters: list[str]` 은 문자열 목록이라 검증이 불가능하므로, `commute_max_minutes` / `budget_yen` / `exclude_wards` 세 개의 타입 있는 필드로 구체화한다.

---

### Task 1: 백엔드 스캐폴딩

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/README.md`
- Create: `backend/src/chika/__init__.py`
- Create: `backend/src/chika/domain/__init__.py`
- Create: `backend/src/chika/domain/model/__init__.py`
- Create: `backend/src/chika/domain/service/__init__.py`
- Create: `backend/src/chika/application/__init__.py`
- Create: `backend/src/chika/application/usecase/__init__.py`
- Create: `backend/src/chika/infrastructure/__init__.py`
- Create: `backend/src/chika/interface/__init__.py`
- Create: `backend/src/chika/etl/__init__.py`
- Test: `backend/tests/test_package.py`

**Interfaces:**
- Consumes: 없음 (최초 태스크)
- Produces: `chika` 패키지가 import 가능. `uv run pytest` / `uv run ruff check .` / `uv run mypy src` 가 동작.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/test_package.py`:

```python
def test_package_imports() -> None:
    import chika

    assert chika.__name__ == "chika"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/test_package.py -v`
Expected: FAIL — `pyproject.toml` 이 없어 `uv run` 이 프로젝트를 찾지 못하거나 `ModuleNotFoundError: No module named 'chika'`

- [ ] **Step 3: 최소 구현**

`backend/.python-version`:

```
3.12
```

`backend/pyproject.toml`:

```toml
[project]
name = "chika"
version = "0.1.0"
description = "Chika Lens - Tokyo living-area analysis agent"
requires-python = ">=3.12,<3.13"
dependencies = []

[project.optional-dependencies]
agent = ["openai-agents>=0.1.0", "pydantic>=2.7"]
etl = ["shapely>=2.0", "pyproj>=3.6"]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chika"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "TID"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"pydantic".msg = "domain/application 계층에서 금지. interface 계층에서만 사용."

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
```

패키지 디렉터리와 빈 `__init__.py` 를 만든다:

```bash
cd backend
mkdir -p src/chika/domain/model src/chika/domain/service \
         src/chika/application/usecase src/chika/infrastructure \
         src/chika/interface src/chika/etl tests
touch src/chika/__init__.py \
      src/chika/domain/__init__.py src/chika/domain/model/__init__.py \
      src/chika/domain/service/__init__.py \
      src/chika/application/__init__.py src/chika/application/usecase/__init__.py \
      src/chika/infrastructure/__init__.py src/chika/interface/__init__.py \
      src/chika/etl/__init__.py
uv python pin 3.12
uv sync
```

`backend/README.md`:

```markdown
# Chika Lens Backend

## 개발

    uv sync
    uv run pytest
    uv run ruff check .
    uv run mypy src

## 계층 규칙

- `domain` — 표준 라이브러리만. 외부 패키지 import 금지.
- `application` — `domain` 만 import.
- `infrastructure` / `interface` — 자유. 단 `domain` 을 향해서만 의존한다.
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run ruff check . && uv run mypy src`
Expected: 1 passed, ruff/mypy 통과

- [ ] **Step 5: 커밋**

```bash
git add backend/
git commit -m "chore: 백엔드 스캐폴딩 (uv + pytest + ruff + mypy)"
```

---

### Task 2: 지표 모델 (MetricKey, RawMetrics, AreaMetrics, Station)

**Files:**
- Create: `backend/src/chika/domain/model/metrics.py`
- Create: `backend/src/chika/domain/model/station.py`
- Test: `backend/tests/domain/model/test_metrics.py`
- Test: `backend/tests/domain/model/test_station.py`

**Interfaces:**
- Consumes: Task 1의 패키지 구조
- Produces:
  - `MetricKey(StrEnum)` — 15개 멤버
  - `NEGATIVE_METRICS: frozenset[MetricKey]`
  - `WARD_RESOLUTION_METRICS: frozenset[MetricKey]`
  - `RawMetrics(station_id: str, values: Mapping[MetricKey, float | None])`
  - `AreaMetrics(station_id: str, percentile: Mapping[MetricKey, float], missing: frozenset[MetricKey])`
    - `AreaMetrics.is_ward_resolution(key: MetricKey) -> bool`
  - `Station(id: str, name_ja: str, name_ko: str, ward: str, lat: float, lon: float, lines: tuple[str, ...])`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/domain/model/test_metrics.py`:

```python
import pytest

from chika.domain.model.metrics import (
    NEGATIVE_METRICS,
    WARD_RESOLUTION_METRICS,
    AreaMetrics,
    MetricKey,
    RawMetrics,
)


def test_there_are_exactly_15_metrics() -> None:
    assert len(MetricKey) == 15


def test_negative_metrics_are_the_three_penalty_axes() -> None:
    assert NEGATIVE_METRICS == frozenset(
        {MetricKey.PRICE_LEVEL, MetricKey.DISASTER_RISK, MetricKey.NUISANCE_VENUE}
    )


def test_ward_resolution_metric_is_flagged() -> None:
    assert MetricKey.KOREAN_RESIDENT_RATIO in WARD_RESOLUTION_METRICS
    assert MetricKey.KOREAN_RESTAURANT not in WARD_RESOLUTION_METRICS


def test_raw_metrics_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        RawMetrics(station_id="s1", values={"not_a_metric": 1.0})  # type: ignore[dict-item]


def test_area_metrics_requires_all_15_percentiles() -> None:
    with pytest.raises(ValueError, match="missing percentile"):
        AreaMetrics(
            station_id="s1",
            percentile={MetricKey.CAFE: 50.0},
            missing=frozenset(),
        )


def test_area_metrics_reports_ward_resolution() -> None:
    area = AreaMetrics(
        station_id="s1",
        percentile={key: 50.0 for key in MetricKey},
        missing=frozenset(),
    )
    assert area.is_ward_resolution(MetricKey.KOREAN_RESIDENT_RATIO) is True
    assert area.is_ward_resolution(MetricKey.CAFE) is False
```

`backend/tests/domain/model/test_station.py`:

```python
import pytest

from chika.domain.model.station import Station


def test_station_is_frozen() -> None:
    station = Station(
        id="nakano",
        name_ja="中野",
        name_ko="나카노",
        ward="中野区",
        lat=35.7056,
        lon=139.6659,
        lines=("JR中央線",),
    )
    with pytest.raises(AttributeError):
        station.ward = "新宿区"  # type: ignore[misc]


def test_station_rejects_coordinates_outside_tokyo() -> None:
    with pytest.raises(ValueError, match="outside Tokyo"):
        Station(
            id="busan",
            name_ja="釜山",
            name_ko="부산",
            ward="中野区",
            lat=35.1,
            lon=129.0,
            lines=(),
        )
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.metrics'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/domain/model/metrics.py`:

```python
"""지표 정의. 15개 지표 키의 유일한 정의처."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

NEUTRAL_PERCENTILE = 50.0


class MetricKey(StrEnum):
    """스펙 §6.2의 지표 15개. 순서는 스펙 표의 번호와 같다."""

    KOREAN_RESTAURANT = "korean_restaurant"          # 1
    KOREAN_GROCERY = "korean_grocery"                # 2
    KOREAN_RESIDENT_RATIO = "korean_resident_ratio"  # 3
    SUPERMARKET = "supermarket"                      # 4
    CONVENIENCE_STORE = "convenience_store"          # 5
    HEALTHCARE = "healthcare"                        # 6
    CAFE = "cafe"                                    # 7
    PARK = "park"                                    # 8
    FITNESS = "fitness"                              # 9
    RESTAURANT_VARIETY = "restaurant_variety"        # 10
    CHILDCARE_EDUCATION = "childcare_education"      # 11
    GOOD_FOR_CHILDREN = "good_for_children"          # 12
    PRICE_LEVEL = "price_level"                      # 13 (감점)
    DISASTER_RISK = "disaster_risk"                  # 14 (감점)
    NUISANCE_VENUE = "nuisance_venue"                # 15 (감점)


#: 원시값이 높을수록 나쁜 지표. 정규화 단계에서 퍼센타일을 뒤집는다.
NEGATIVE_METRICS: frozenset[MetricKey] = frozenset(
    {MetricKey.PRICE_LEVEL, MetricKey.DISASTER_RISK, MetricKey.NUISANCE_VENUE}
)

#: 역세권이 아니라 구 단위 해상도인 지표. 화면에 반드시 명시해야 한다 (스펙 §3.2).
WARD_RESOLUTION_METRICS: frozenset[MetricKey] = frozenset({MetricKey.KOREAN_RESIDENT_RATIO})


@dataclass(frozen=True)
class RawMetrics:
    """정규화 이전의 원시 지표값. `None` 은 결측을 뜻한다."""

    station_id: str
    values: Mapping[MetricKey, float | None]

    def __post_init__(self) -> None:
        for key in self.values:
            if not isinstance(key, MetricKey):
                raise ValueError(f"unknown metric: {key!r}")

    def get(self, key: MetricKey) -> float | None:
        return self.values.get(key)


@dataclass(frozen=True)
class AreaMetrics:
    """정규화된 퍼센타일(0~100). 전 지표가 '높을수록 좋음'으로 통일되어 있다."""

    station_id: str
    percentile: Mapping[MetricKey, float]
    missing: frozenset[MetricKey]

    def __post_init__(self) -> None:
        absent = [key for key in MetricKey if key not in self.percentile]
        if absent:
            raise ValueError(f"missing percentile for: {[k.value for k in absent]}")

    def is_ward_resolution(self, key: MetricKey) -> bool:
        return key in WARD_RESOLUTION_METRICS
```

`backend/src/chika/domain/model/station.py`:

```python
"""역 마스터. 분석 단위는 역 반경 800m (스펙 §6.1)."""

from __future__ import annotations

from dataclasses import dataclass

#: 도쿄 23구를 넉넉히 감싸는 경계 상자. 좌표 오염을 조기에 잡기 위한 방어선.
TOKYO_BBOX = (35.50, 35.85, 139.55, 139.95)  # lat_min, lat_max, lon_min, lon_max

STATION_RADIUS_METERS = 800


@dataclass(frozen=True)
class Station:
    id: str
    name_ja: str
    name_ko: str
    ward: str
    lat: float
    lon: float
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        lat_min, lat_max, lon_min, lon_max = TOKYO_BBOX
        if not (lat_min <= self.lat <= lat_max and lon_min <= self.lon <= lon_max):
            raise ValueError(
                f"station {self.id!r} is outside Tokyo: ({self.lat}, {self.lon})"
            )
```

`backend/tests/__init__.py`, `backend/tests/domain/__init__.py`, `backend/tests/domain/model/__init__.py` 는 만들지 않는다 (pytest rootdir + `pythonpath` 설정으로 충분).

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v && uv run mypy src`
Expected: 8 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/domain/model backend/tests/domain
git commit -m "feat: 지표 15개와 역 마스터 도메인 모델"
```

---

### Task 3: 다이얼과 가중치 (Dial, DialSettings, Weights, expand_dials)

**Files:**
- Create: `backend/src/chika/domain/model/weights.py`
- Create: `backend/src/chika/domain/service/dials.py`
- Test: `backend/tests/domain/model/test_weights.py`
- Test: `backend/tests/domain/service/test_dials.py`

**Interfaces:**
- Consumes: `MetricKey` (Task 2)
- Produces:
  - `Dial(StrEnum)` — `KOREAN_LIFE`, `DAILY_CONVENIENCE`, `QUALITY_OF_LIFE`, `FAMILY`, `COST_RISK`
  - `DialSettings(values: Mapping[Dial, float])`, `DialSettings.balanced() -> DialSettings`
  - `Weights(values: Mapping[MetricKey, float])` — 합이 1.0, `__getitem__`, `items()`
  - `Weights.normalized(raw: Mapping[MetricKey, float]) -> Weights`
  - `DIAL_TO_METRICS: Mapping[Dial, tuple[MetricKey, ...]]`
  - `expand_dials(settings: DialSettings) -> Weights`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/domain/model/test_weights.py`:

```python
import pytest

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings, Weights


def test_weights_normalize_to_one() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 3.0, MetricKey.PARK: 1.0})
    assert weights[MetricKey.CAFE] == pytest.approx(0.75)
    assert weights[MetricKey.PARK] == pytest.approx(0.25)
    assert sum(v for _, v in weights.items()) == pytest.approx(1.0)


def test_unlisted_metric_has_zero_weight() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    assert weights[MetricKey.DISASTER_RISK] == 0.0


def test_all_zero_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to zero"):
        Weights.normalized({MetricKey.CAFE: 0.0})


def test_negative_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative weight"):
        Weights.normalized({MetricKey.CAFE: -1.0})


def test_there_are_exactly_5_dials() -> None:
    assert len(Dial) == 5


def test_balanced_dial_settings_are_all_equal() -> None:
    settings = DialSettings.balanced()
    assert set(settings.values) == set(Dial)
    assert len(set(settings.values.values())) == 1
```

`backend/tests/domain/service/test_dials.py`:

```python
import pytest

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import DIAL_TO_METRICS, expand_dials


def test_every_metric_belongs_to_exactly_one_dial() -> None:
    covered = [metric for metrics in DIAL_TO_METRICS.values() for metric in metrics]
    assert sorted(covered) == sorted(MetricKey)


def test_dial_mapping_matches_spec() -> None:
    assert DIAL_TO_METRICS[Dial.KOREAN_LIFE] == (
        MetricKey.KOREAN_RESTAURANT,
        MetricKey.KOREAN_GROCERY,
        MetricKey.KOREAN_RESIDENT_RATIO,
    )
    assert DIAL_TO_METRICS[Dial.FAMILY] == (
        MetricKey.CHILDCARE_EDUCATION,
        MetricKey.GOOD_FOR_CHILDREN,
    )


def test_single_dial_spreads_evenly_over_its_metrics() -> None:
    weights = expand_dials(DialSettings({Dial.FAMILY: 1.0}))
    assert weights[MetricKey.CHILDCARE_EDUCATION] == pytest.approx(0.5)
    assert weights[MetricKey.GOOD_FOR_CHILDREN] == pytest.approx(0.5)
    assert weights[MetricKey.CAFE] == 0.0


def test_dial_strength_is_relative_not_absolute() -> None:
    a = expand_dials(DialSettings({Dial.FAMILY: 1.0, Dial.COST_RISK: 1.0}))
    b = expand_dials(DialSettings({Dial.FAMILY: 5.0, Dial.COST_RISK: 5.0}))
    for metric in MetricKey:
        assert a[metric] == pytest.approx(b[metric])


def test_expanded_weights_always_sum_to_one() -> None:
    weights = expand_dials(
        DialSettings({Dial.KOREAN_LIFE: 3.0, Dial.DAILY_CONVENIENCE: 1.0, Dial.COST_RISK: 2.0})
    )
    assert sum(v for _, v in weights.items()) == pytest.approx(1.0)


def test_all_dials_zero_falls_back_to_balanced() -> None:
    weights = expand_dials(DialSettings({dial: 0.0 for dial in Dial}))
    balanced = expand_dials(DialSettings.balanced())
    for metric in MetricKey:
        assert weights[metric] == pytest.approx(balanced[metric])
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.weights'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/domain/model/weights.py`:

```python
"""가중치 값 객체. 합은 항상 1.0으로 정규화된다."""

from __future__ import annotations

from collections.abc import ItemsView, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from chika.domain.model.metrics import MetricKey


class Dial(StrEnum):
    """사용자 관점 다이얼 5개. LLM이 정하는 것은 이 5개의 상대 강도뿐이다 (스펙 §6.4)."""

    KOREAN_LIFE = "korean_life"
    DAILY_CONVENIENCE = "daily_convenience"
    QUALITY_OF_LIFE = "quality_of_life"
    FAMILY = "family"
    COST_RISK = "cost_risk"


@dataclass(frozen=True)
class DialSettings:
    values: Mapping[Dial, float]

    def __post_init__(self) -> None:
        for dial, strength in self.values.items():
            if not isinstance(dial, Dial):
                raise ValueError(f"unknown dial: {dial!r}")
            if strength < 0:
                raise ValueError(f"negative dial strength for {dial.value}: {strength}")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def strength(self, dial: Dial) -> float:
        return self.values.get(dial, 0.0)

    @classmethod
    def balanced(cls) -> DialSettings:
        return cls({dial: 1.0 for dial in Dial})


@dataclass(frozen=True)
class Weights:
    """지표 15개에 대한 가중치. 명시되지 않은 지표는 0."""

    values: Mapping[MetricKey, float]

    def __getitem__(self, key: MetricKey) -> float:
        return self.values.get(key, 0.0)

    def items(self) -> ItemsView[MetricKey, float]:
        return self.values.items()

    @classmethod
    def normalized(cls, raw: Mapping[MetricKey, float]) -> Weights:
        for key, value in raw.items():
            if not isinstance(key, MetricKey):
                raise ValueError(f"unknown metric: {key!r}")
            if value < 0:
                raise ValueError(f"negative weight for {key.value}: {value}")
        total = sum(raw.values())
        if total == 0:
            raise ValueError("weights sum to zero")
        return cls(MappingProxyType({key: value / total for key, value in raw.items()}))
```

`backend/src/chika/domain/service/dials.py`:

```python
"""다이얼 5개 → 지표 15개 가중치 전개 (스펙 §6.4의 고정 매핑 표)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from chika.domain.model.metrics import MetricKey
from chika.domain.model.weights import Dial, DialSettings, Weights

DIAL_TO_METRICS: Mapping[Dial, tuple[MetricKey, ...]] = MappingProxyType(
    {
        Dial.KOREAN_LIFE: (
            MetricKey.KOREAN_RESTAURANT,
            MetricKey.KOREAN_GROCERY,
            MetricKey.KOREAN_RESIDENT_RATIO,
        ),
        Dial.DAILY_CONVENIENCE: (
            MetricKey.SUPERMARKET,
            MetricKey.CONVENIENCE_STORE,
            MetricKey.HEALTHCARE,
        ),
        Dial.QUALITY_OF_LIFE: (
            MetricKey.CAFE,
            MetricKey.PARK,
            MetricKey.FITNESS,
            MetricKey.RESTAURANT_VARIETY,
        ),
        Dial.FAMILY: (
            MetricKey.CHILDCARE_EDUCATION,
            MetricKey.GOOD_FOR_CHILDREN,
        ),
        Dial.COST_RISK: (
            MetricKey.PRICE_LEVEL,
            MetricKey.DISASTER_RISK,
            MetricKey.NUISANCE_VENUE,
        ),
    }
)


def expand_dials(settings: DialSettings) -> Weights:
    """다이얼 강도를 소속 지표에 균등 분배한 뒤 합이 1이 되도록 정규화한다.

    모든 다이얼이 0이면 균등 다이얼로 대체한다 — 랭킹을 못 내는 것보다 낫다.
    """
    if all(settings.strength(dial) == 0.0 for dial in Dial):
        settings = DialSettings.balanced()

    raw: dict[MetricKey, float] = {}
    for dial, metrics in DIAL_TO_METRICS.items():
        share = settings.strength(dial) / len(metrics)
        for metric in metrics:
            raw[metric] = share
    return Weights.normalized(raw)
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v && uv run mypy src`
Expected: 20 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/domain backend/tests/domain
git commit -m "feat: 다이얼 5개를 지표 15개 가중치로 펼치는 매핑"
```

---

### Task 4: 퍼센타일 랭크 정규화

**Files:**
- Create: `backend/src/chika/domain/service/normalization.py`
- Test: `backend/tests/domain/service/test_normalization.py`

**Interfaces:**
- Consumes: `MetricKey`, `NEGATIVE_METRICS`, `NEUTRAL_PERCENTILE`, `RawMetrics`, `AreaMetrics` (Task 2)
- Produces:
  - `percentile_rank(value: float, population: Sequence[float]) -> float`
  - `normalize(raws: Sequence[RawMetrics]) -> list[AreaMetrics]` — 입력 순서를 유지한다

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/domain/service/test_normalization.py`:

```python
import pytest

from chika.domain.model.metrics import NEUTRAL_PERCENTILE, MetricKey, RawMetrics
from chika.domain.service.normalization import normalize, percentile_rank


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    """지정하지 않은 지표는 모두 0.0으로 채운다."""
    filled: dict[MetricKey, float | None] = {key: 0.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def test_percentile_rank_of_single_value_is_50() -> None:
    assert percentile_rank(7.0, [7.0]) == pytest.approx(50.0)


def test_percentile_rank_uses_mid_rank_for_ties() -> None:
    # 값 4개 중 1개가 아래, 2개가 동률 -> (1 + 0.5*2) / 4 = 50%
    assert percentile_rank(5.0, [1.0, 5.0, 5.0, 9.0]) == pytest.approx(50.0)


def test_percentile_rank_of_maximum_is_high() -> None:
    assert percentile_rank(9.0, [1.0, 5.0, 9.0]) == pytest.approx(100.0 * 2.5 / 3)


def test_positive_metric_higher_raw_gives_higher_percentile() -> None:
    areas = normalize(
        [
            _raw("low", cafe=1.0),
            _raw("high", cafe=100.0),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["high"].percentile[MetricKey.CAFE] > by_id["low"].percentile[MetricKey.CAFE]


def test_negative_metric_is_inverted() -> None:
    areas = normalize(
        [
            _raw("cheap", price_level=100_000.0),
            _raw("expensive", price_level=300_000.0),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["cheap"].percentile[MetricKey.PRICE_LEVEL] > (
        by_id["expensive"].percentile[MetricKey.PRICE_LEVEL]
    )


def test_missing_value_gets_neutral_percentile_and_a_flag() -> None:
    areas = normalize(
        [
            _raw("known", cafe=10.0),
            _raw("unknown", cafe=None),
        ]
    )
    by_id = {a.station_id: a for a in areas}
    assert by_id["unknown"].percentile[MetricKey.CAFE] == NEUTRAL_PERCENTILE
    assert MetricKey.CAFE in by_id["unknown"].missing
    assert MetricKey.CAFE not in by_id["known"].missing


def test_missing_values_are_excluded_from_the_population() -> None:
    # cafe 관측치는 10.0 하나뿐 -> 그 하나는 percentile 50 이어야 한다
    areas = normalize([_raw("a", cafe=10.0), _raw("b", cafe=None), _raw("c", cafe=None)])
    by_id = {a.station_id: a for a in areas}
    assert by_id["a"].percentile[MetricKey.CAFE] == pytest.approx(NEUTRAL_PERCENTILE)


def test_metric_missing_everywhere_is_neutral_and_flagged_everywhere() -> None:
    areas = normalize([_raw("a", cafe=None), _raw("b", cafe=None)])
    for area in areas:
        assert area.percentile[MetricKey.CAFE] == NEUTRAL_PERCENTILE
        assert MetricKey.CAFE in area.missing


def test_input_order_is_preserved() -> None:
    areas = normalize([_raw("z"), _raw("a"), _raw("m")])
    assert [a.station_id for a in areas] == ["z", "a", "m"]


def test_normalize_of_empty_input_is_empty() -> None:
    assert normalize([]) == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/domain/service/test_normalization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.service.normalization'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/domain/service/normalization.py`:

```python
"""퍼센타일 랭크 정규화 (스펙 §6.3).

z-score를 쓰지 않는다. 도쿄 상권은 롱테일이라 신주쿠·시부야 같은 극단값이
분산을 지배해 나머지 역들이 전부 평균 근처로 뭉개진다.
"""

from __future__ import annotations

from collections.abc import Sequence

from chika.domain.model.metrics import (
    NEGATIVE_METRICS,
    NEUTRAL_PERCENTILE,
    AreaMetrics,
    MetricKey,
    RawMetrics,
)


def percentile_rank(value: float, population: Sequence[float]) -> float:
    """동률을 절반으로 세는 mid-rank 퍼센타일 (0~100).

    값이 하나뿐이면 50이 되어 결측 중립값과 자연스럽게 맞물린다.
    """
    n = len(population)
    if n == 0:
        return NEUTRAL_PERCENTILE
    below = sum(1 for other in population if other < value)
    equal = sum(1 for other in population if other == value)
    return 100.0 * (below + 0.5 * equal) / n


def normalize(raws: Sequence[RawMetrics]) -> list[AreaMetrics]:
    """전체 역 집합 안에서 지표별 퍼센타일을 매긴다.

    감점 지표는 `100 - p` 로 뒤집어 이후 계층 전체를 '높을수록 좋음'으로 통일한다.
    결측은 중립값 50이지만 `missing` 에 반드시 기록된다 — 조용히 채우면 거짓말이 된다.
    """
    if not raws:
        return []

    populations: dict[MetricKey, list[float]] = {
        key: [v for raw in raws if (v := raw.get(key)) is not None] for key in MetricKey
    }

    areas: list[AreaMetrics] = []
    for raw in raws:
        percentile: dict[MetricKey, float] = {}
        missing: set[MetricKey] = set()
        for key in MetricKey:
            value = raw.get(key)
            if value is None:
                percentile[key] = NEUTRAL_PERCENTILE
                missing.add(key)
                continue
            rank = percentile_rank(value, populations[key])
            percentile[key] = 100.0 - rank if key in NEGATIVE_METRICS else rank
        areas.append(
            AreaMetrics(
                station_id=raw.station_id,
                percentile=percentile,
                missing=frozenset(missing),
            )
        )
    return areas
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v && uv run mypy src`
Expected: 30 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/domain/service/normalization.py backend/tests/domain/service/test_normalization.py
git commit -m "feat: 퍼센타일 랭크 정규화와 결측 플래그"
```

---

### Task 5: 스코어링 (AreaScore, score, rank)

**Files:**
- Create: `backend/src/chika/domain/model/score.py`
- Create: `backend/src/chika/domain/service/scoring.py`
- Test: `backend/tests/domain/service/test_scoring.py`

**Interfaces:**
- Consumes: `AreaMetrics`, `MetricKey` (Task 2), `Weights` (Task 3)
- Produces:
  - `AreaScore(station_id: str, total: float, contributions: Mapping[MetricKey, float], missing: frozenset[MetricKey])`
    - `.top_drivers(n: int = 3) -> list[tuple[MetricKey, float]]`
    - `.bottom_drivers(n: int = 3) -> list[tuple[MetricKey, float]]`
  - `score(area: AreaMetrics, weights: Weights) -> AreaScore`
  - `rank(areas: Sequence[AreaMetrics], weights: Weights) -> list[AreaScore]`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/domain/service/test_scoring.py`:

```python
import pytest

from chika.domain.model.metrics import AreaMetrics, MetricKey
from chika.domain.model.weights import Weights
from chika.domain.service.scoring import rank, score


def _area(station_id: str, **percentiles: float) -> AreaMetrics:
    filled = {key: 50.0 for key in MetricKey}
    for name, value in percentiles.items():
        filled[MetricKey(name)] = value
    return AreaMetrics(station_id=station_id, percentile=filled, missing=frozenset())


def test_all_neutral_percentiles_score_50() -> None:
    result = score(_area("s1"), Weights.normalized({key: 1.0 for key in MetricKey}))
    assert result.total == pytest.approx(50.0)


def test_zero_weight_metric_does_not_affect_total() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    high = score(_area("s1", park=100.0), weights)
    low = score(_area("s2", park=0.0), weights)
    assert high.total == pytest.approx(low.total)


def test_contribution_is_weight_times_deviation_from_50() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    result = score(_area("s1", cafe=90.0), weights)
    assert result.contributions[MetricKey.CAFE] == pytest.approx(40.0)
    assert result.total == pytest.approx(90.0)


def test_low_percentile_pulls_the_total_down() -> None:
    weights = Weights.normalized({MetricKey.PRICE_LEVEL: 1.0})
    result = score(_area("s1", price_level=10.0), weights)
    assert result.total == pytest.approx(10.0)
    assert result.contributions[MetricKey.PRICE_LEVEL] < 0


def test_missing_flags_propagate_into_the_score() -> None:
    area = AreaMetrics(
        station_id="s1",
        percentile={key: 50.0 for key in MetricKey},
        missing=frozenset({MetricKey.KOREAN_GROCERY}),
    )
    result = score(area, Weights.normalized({MetricKey.CAFE: 1.0}))
    assert MetricKey.KOREAN_GROCERY in result.missing


def test_top_and_bottom_drivers_are_sorted_by_contribution() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0, MetricKey.PARK: 1.0, MetricKey.FITNESS: 1.0})
    result = score(_area("s1", cafe=100.0, park=0.0, fitness=60.0), weights)
    assert [key for key, _ in result.top_drivers(2)] == [MetricKey.CAFE, MetricKey.FITNESS]
    assert result.bottom_drivers(1)[0][0] == MetricKey.PARK


def test_rank_orders_by_total_descending() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    ranked = rank([_area("mid", cafe=50.0), _area("top", cafe=99.0), _area("bot", cafe=1.0)], weights)
    assert [r.station_id for r in ranked] == ["top", "mid", "bot"]


def test_rank_breaks_ties_by_station_id_for_determinism() -> None:
    weights = Weights.normalized({MetricKey.CAFE: 1.0})
    ranked = rank([_area("b", cafe=70.0), _area("a", cafe=70.0)], weights)
    assert [r.station_id for r in ranked] == ["a", "b"]


def test_score_stays_within_0_and_100() -> None:
    weights = Weights.normalized({key: 1.0 for key in MetricKey})
    best = score(_area("best", **{key.value: 100.0 for key in MetricKey}), weights)
    worst = score(_area("worst", **{key.value: 0.0 for key in MetricKey}), weights)
    assert best.total == pytest.approx(100.0)
    assert worst.total == pytest.approx(0.0)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/domain/service/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.service.scoring'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/domain/model/score.py`:

```python
"""점수와 지표별 기여도. 기여도가 있어야 LLM이 이유를 지어내지 않는다."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chika.domain.model.metrics import MetricKey


@dataclass(frozen=True)
class AreaScore:
    station_id: str
    total: float
    contributions: Mapping[MetricKey, float]
    missing: frozenset[MetricKey]

    def _sorted(self) -> list[tuple[MetricKey, float]]:
        return sorted(
            self.contributions.items(),
            key=lambda item: (-item[1], item[0].value),
        )

    def top_drivers(self, n: int = 3) -> list[tuple[MetricKey, float]]:
        return self._sorted()[:n]

    def bottom_drivers(self, n: int = 3) -> list[tuple[MetricKey, float]]:
        return list(reversed(self._sorted()))[:n]
```

`backend/src/chika/domain/service/scoring.py`:

```python
"""점수 계산 (스펙 §6.4). 외부 의존 0, 순수 함수.

LLM은 여기 있는 어떤 수치도 계산하지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

from chika.domain.model.metrics import NEUTRAL_PERCENTILE, AreaMetrics, MetricKey
from chika.domain.model.score import AreaScore
from chika.domain.model.weights import Weights


def score(area: AreaMetrics, weights: Weights) -> AreaScore:
    contributions = {
        key: weights[key] * (area.percentile[key] - NEUTRAL_PERCENTILE) for key in MetricKey
    }
    return AreaScore(
        station_id=area.station_id,
        total=NEUTRAL_PERCENTILE + sum(contributions.values()),
        contributions=contributions,
        missing=area.missing,
    )


def rank(areas: Sequence[AreaMetrics], weights: Weights) -> list[AreaScore]:
    """총점 내림차순. 동점은 station_id 오름차순으로 깨서 결과를 결정적으로 만든다."""
    scores = [score(area, weights) for area in areas]
    return sorted(scores, key=lambda s: (-s.total, s.station_id))
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v && uv run mypy src`
Expected: 39 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/domain backend/tests/domain
git commit -m "feat: 지표 기여도 분해가 포함된 스코어링 서비스"
```

---

### Task 6: 검색 조건과 리포지토리 포트

**Files:**
- Create: `backend/src/chika/domain/model/criteria.py`
- Create: `backend/src/chika/domain/repository.py`
- Test: `backend/tests/domain/model/test_criteria.py`

**Interfaces:**
- Consumes: `DialSettings` (Task 3)
- Produces:
  - `Household(StrEnum)` — `SINGLE`, `COUPLE`, `FAMILY`
  - `SearchCriteria(dials, commute_to=None, commute_max_minutes=None, budget_yen=None, household=Household.SINGLE, exclude_wards=())`
    - `.replace(**changes) -> SearchCriteria` — 대화 중 조건 일부만 교체 (스펙 §5.5)
  - `AreaMetricsRepository(Protocol)` — `stations() -> Sequence[Station]`, `raw_metrics() -> Sequence[RawMetrics]`
  - `CommuteRepository(Protocol)` — `minutes_to(origin_station_id: str, dest_station_id: str) -> int | None`
  - `PriceRepository(Protocol)` — `median_rent_yen(station_id: str, household: Household) -> int | None`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/domain/model/test_criteria.py`:

```python
import pytest

from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.weights import Dial, DialSettings


def _criteria(**overrides: object) -> SearchCriteria:
    base: dict[str, object] = {"dials": DialSettings.balanced()}
    base.update(overrides)
    return SearchCriteria(**base)  # type: ignore[arg-type]


def test_defaults_are_unconstrained_single_household() -> None:
    criteria = _criteria()
    assert criteria.commute_to is None
    assert criteria.commute_max_minutes is None
    assert criteria.budget_yen is None
    assert criteria.household is Household.SINGLE
    assert criteria.exclude_wards == ()


def test_replace_changes_only_the_named_field() -> None:
    original = _criteria(budget_yen=(80_000, 150_000), commute_to="shinjuku")
    updated = original.replace(budget_yen=(80_000, 120_000))
    assert updated.budget_yen == (80_000, 120_000)
    assert updated.commute_to == "shinjuku"
    assert original.budget_yen == (80_000, 150_000)  # 원본 불변


def test_replace_can_change_dials() -> None:
    updated = _criteria().replace(dials=DialSettings({Dial.FAMILY: 3.0}))
    assert updated.dials.strength(Dial.FAMILY) == 3.0


def test_inverted_budget_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="budget range"):
        _criteria(budget_yen=(200_000, 100_000))


def test_negative_commute_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="commute limit"):
        _criteria(commute_max_minutes=-5)


def test_commute_limit_without_destination_is_rejected() -> None:
    with pytest.raises(ValueError, match="commute_to"):
        _criteria(commute_max_minutes=30)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/domain/model/test_criteria.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.domain.model.criteria'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/domain/model/criteria.py`:

```python
"""검색 조건. IntakeAgent가 대화에서 채우는 값 객체 (스펙 §5.2).

스펙 원문의 `hard_filters: list[str]` 은 검증이 불가능해
`commute_*` / `budget_yen` / `exclude_wards` 로 구체화했다.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from chika.domain.model.weights import DialSettings


class Household(StrEnum):
    SINGLE = "single"
    COUPLE = "couple"
    FAMILY = "family"


@dataclass(frozen=True)
class SearchCriteria:
    dials: DialSettings
    commute_to: str | None = None
    commute_max_minutes: int | None = None
    budget_yen: tuple[int, int] | None = None
    household: Household = Household.SINGLE
    exclude_wards: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.budget_yen is not None:
            low, high = self.budget_yen
            if low > high:
                raise ValueError(f"invalid budget range: {low} > {high}")
        if self.commute_max_minutes is not None:
            if self.commute_max_minutes < 0:
                raise ValueError(f"invalid commute limit: {self.commute_max_minutes}")
            if self.commute_to is None:
                raise ValueError("commute_max_minutes requires commute_to")

    def replace(self, **changes: Any) -> SearchCriteria:
        """조건 일부만 바꿔 재랭킹할 때 쓴다 (스펙 §5.5, 유스케이스 2.2-2)."""
        return dataclasses.replace(self, **changes)
```

`backend/src/chika/domain/repository.py`:

```python
"""리포지토리 포트. 구현체는 infrastructure 계층에만 존재한다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station


class AreaMetricsRepository(Protocol):
    def stations(self) -> Sequence[Station]: ...

    def raw_metrics(self) -> Sequence[RawMetrics]: ...


class CommuteRepository(Protocol):
    def minutes_to(self, origin_station_id: str, dest_station_id: str) -> int | None:
        """알 수 없으면 None. 하드 필터는 None을 '탈락'이 아니라 '판단 보류'로 다룬다."""
        ...


class PriceRepository(Protocol):
    def median_rent_yen(self, station_id: str, household: Household) -> int | None: ...
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest tests/domain -v && uv run mypy src`
Expected: 45 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/domain backend/tests/domain
git commit -m "feat: SearchCriteria와 리포지토리 포트 정의"
```

---

### Task 7: Fake 리포지토리와 시드 픽스처

**Files:**
- Create: `backend/src/chika/infrastructure/fake/__init__.py`
- Create: `backend/src/chika/infrastructure/fake/repositories.py`
- Create: `backend/src/chika/infrastructure/fake/seed.py`
- Test: `backend/tests/infrastructure/test_fake_repositories.py`

**Interfaces:**
- Consumes: `Station`, `RawMetrics`, `MetricKey`, `Household` (Task 2·6), 포트 Protocol (Task 6)
- Produces:
  - `FakeAreaMetricsRepository(stations, raws)` — `AreaMetricsRepository` 구현
  - `FakeCommuteRepository(table: Mapping[tuple[str, str], int])`
  - `FakePriceRepository(table: Mapping[str, int])`
  - `build_seed(count: int = 40, seed: int = 20260903) -> tuple[list[Station], list[RawMetrics], dict[tuple[str, str], int], dict[str, int]]`
  - `SEED_WARDS: tuple[str, ...]`

**설계 메모:** 시드는 결정적이어야 한다(`random.Random(seed)` 고정). 테스트가 흔들리면 Phase 0의 의미가 없다. 실제 250개 역은 Task 10이 만든다 — 여기서는 유스케이스와 에이전트를 굴릴 최소 규모(40개)면 된다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/infrastructure/test_fake_repositories.py`:

```python
from chika.domain.model.criteria import Household
from chika.domain.model.metrics import MetricKey
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed


def test_seed_is_deterministic() -> None:
    a_stations, a_raws, _, _ = build_seed()
    b_stations, b_raws, _, _ = build_seed()
    assert [s.id for s in a_stations] == [s.id for s in b_stations]
    assert a_raws[0].values == b_raws[0].values


def test_seed_produces_the_requested_number_of_stations() -> None:
    stations, raws, _, _ = build_seed(count=12)
    assert len(stations) == 12
    assert len(raws) == 12
    assert {s.id for s in stations} == {r.station_id for r in raws}


def test_seed_covers_every_metric() -> None:
    _, raws, _, _ = build_seed(count=5)
    for raw in raws:
        assert set(raw.values) == set(MetricKey)


def test_seed_contains_some_missing_values() -> None:
    _, raws, _, _ = build_seed(count=40)
    assert any(value is None for raw in raws for value in raw.values.values())


def test_area_repository_returns_what_it_was_given() -> None:
    stations, raws, _, _ = build_seed(count=6)
    repo = FakeAreaMetricsRepository(stations, raws)
    assert list(repo.stations()) == stations
    assert list(repo.raw_metrics()) == raws


def test_commute_repository_returns_none_for_unknown_pair() -> None:
    repo = FakeCommuteRepository({("a", "b"): 15})
    assert repo.minutes_to("a", "b") == 15
    assert repo.minutes_to("a", "zzz") is None


def test_commute_to_self_is_zero() -> None:
    repo = FakeCommuteRepository({})
    assert repo.minutes_to("a", "a") == 0


def test_price_repository_scales_with_household_size() -> None:
    repo = FakePriceRepository({"a": 100_000})
    assert repo.median_rent_yen("a", Household.SINGLE) == 100_000
    single = repo.median_rent_yen("a", Household.SINGLE)
    family = repo.median_rent_yen("a", Household.FAMILY)
    assert single is not None and family is not None and family > single
    assert repo.median_rent_yen("zzz", Household.SINGLE) is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/infrastructure -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.infrastructure.fake'`

- [ ] **Step 3: 최소 구현**

```bash
mkdir -p backend/src/chika/infrastructure/fake && touch backend/src/chika/infrastructure/fake/__init__.py
```

`backend/src/chika/infrastructure/fake/repositories.py`:

```python
"""Fake 리포지토리. Phase 1~2에서 BigQuery/MLIT 어댑터로 교체된다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from chika.domain.model.criteria import Household
from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station

#: 가구 유형별 임대료 배수. Phase 1에서 MLIT 실거래 통계로 대체된다.
HOUSEHOLD_RENT_MULTIPLIER: Mapping[Household, float] = {
    Household.SINGLE: 1.0,
    Household.COUPLE: 1.45,
    Household.FAMILY: 1.9,
}


class FakeAreaMetricsRepository:
    def __init__(self, stations: Sequence[Station], raws: Sequence[RawMetrics]) -> None:
        self._stations = list(stations)
        self._raws = list(raws)

    def stations(self) -> Sequence[Station]:
        return self._stations

    def raw_metrics(self) -> Sequence[RawMetrics]:
        return self._raws


class FakeCommuteRepository:
    def __init__(self, table: Mapping[tuple[str, str], int]) -> None:
        self._table = dict(table)

    def minutes_to(self, origin_station_id: str, dest_station_id: str) -> int | None:
        if origin_station_id == dest_station_id:
            return 0
        return self._table.get((origin_station_id, dest_station_id))


class FakePriceRepository:
    def __init__(self, table: Mapping[str, int]) -> None:
        self._table = dict(table)

    def median_rent_yen(self, station_id: str, household: Household) -> int | None:
        base = self._table.get(station_id)
        if base is None:
            return None
        return round(base * HOUSEHOLD_RENT_MULTIPLIER[household])
```

`backend/src/chika/infrastructure/fake/seed.py`:

```python
"""결정적 시드 데이터. 실제 데이터가 오기 전까지 전 계층을 굴리기 위한 것."""

from __future__ import annotations

import random

from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station

SEED_WARDS: tuple[str, ...] = (
    "新宿区",
    "渋谷区",
    "中野区",
    "杉並区",
    "豊島区",
    "板橋区",
    "北区",
    "足立区",
)

#: 지표별 (최소, 최대) 원시값 범위. 스케일이 제각각인 상황을 일부러 재현한다.
_METRIC_RANGE: dict[MetricKey, tuple[float, float]] = {
    MetricKey.KOREAN_RESTAURANT: (0.0, 40.0),
    MetricKey.KOREAN_GROCERY: (0.0, 8.0),
    MetricKey.KOREAN_RESIDENT_RATIO: (0.002, 0.05),
    MetricKey.SUPERMARKET: (1.0, 25.0),
    MetricKey.CONVENIENCE_STORE: (3.0, 80.0),
    MetricKey.HEALTHCARE: (2.0, 60.0),
    MetricKey.CAFE: (1.0, 90.0),
    MetricKey.PARK: (0.0, 15.0),
    MetricKey.FITNESS: (0.0, 12.0),
    MetricKey.RESTAURANT_VARIETY: (5.0, 70.0),
    MetricKey.CHILDCARE_EDUCATION: (1.0, 30.0),
    MetricKey.GOOD_FOR_CHILDREN: (0.0, 1.0),
    MetricKey.PRICE_LEVEL: (80_000.0, 260_000.0),
    MetricKey.DISASTER_RISK: (0.0, 1.0),
    MetricKey.NUISANCE_VENUE: (0.0, 20.0),
}

#: 결측을 일부러 섞는다. 결측 플래그 경로가 시드에서도 살아 있어야 한다.
_MISSING_PROBABILITY = 0.05


def build_seed(
    count: int = 40,
    seed: int = 20260903,
) -> tuple[list[Station], list[RawMetrics], dict[tuple[str, str], int], dict[str, int]]:
    """(역, 원시지표, 통근시간표, 시세표)를 결정적으로 만든다."""
    rng = random.Random(seed)

    stations: list[Station] = []
    raws: list[RawMetrics] = []
    prices: dict[str, int] = {}

    for index in range(count):
        station_id = f"seed_{index:03d}"
        stations.append(
            Station(
                id=station_id,
                name_ja=f"仮駅{index:03d}",
                name_ko=f"가상역{index:03d}",
                ward=SEED_WARDS[index % len(SEED_WARDS)],
                lat=35.65 + rng.uniform(0.0, 0.15),
                lon=139.62 + rng.uniform(0.0, 0.25),
                lines=(f"仮線{index % 5}",),
            )
        )

        values: dict[MetricKey, float | None] = {}
        for key, (low, high) in _METRIC_RANGE.items():
            if rng.random() < _MISSING_PROBABILITY:
                values[key] = None
            else:
                values[key] = round(rng.uniform(low, high), 4)
        raws.append(RawMetrics(station_id=station_id, values=values))

        price = values[MetricKey.PRICE_LEVEL]
        prices[station_id] = int(price) if price is not None else 130_000

    # 통근: 시드 역 전부에서 seed_000(=도심 대용)까지의 소요시간
    hub = stations[0].id
    commute = {(station.id, hub): 5 + (i * 3) % 55 for i, station in enumerate(stations)}

    return stations, raws, commute, prices
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run mypy src`
Expected: 53 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/infrastructure backend/tests/infrastructure
git commit -m "feat: Fake 리포지토리와 결정적 시드 데이터"
```

---

### Task 8: RankAreas 유스케이스

**Files:**
- Create: `backend/src/chika/application/usecase/rank_areas.py`
- Test: `backend/tests/application/test_rank_areas.py`

**Interfaces:**
- Consumes: `normalize` (Task 4), `rank`/`score` (Task 5), `expand_dials` (Task 3), `SearchCriteria`/포트 (Task 6), Fake 구현 (Task 7)
- Produces:
  - `RankedArea(station: Station, score: AreaScore, rent_yen: int | None, commute_minutes: int | None)`
  - `RankAreas(areas: AreaMetricsRepository, commute: CommuteRepository, prices: PriceRepository)`
    - `.execute(criteria: SearchCriteria, limit: int = 5) -> list[RankedArea]`

**설계 메모 (중요):** 퍼센타일은 **하드 필터 적용 전, 전체 역 집합**에서 계산한다. 스펙 §6.3의 "250개 역 안에서"가 그 뜻이다. 필터를 먼저 걸면 사용자가 예산을 바꿀 때마다 모집단이 달라져 "상위 12%"라는 표현이 무의미해진다.

통근 시간을 모르는 역(`None`)은 **탈락시키지 않는다**. 데이터 부재를 부정 판정으로 바꾸면 Phase 0 시드에서 대부분의 역이 사라진다. 대신 `commute_minutes=None` 으로 그대로 노출해 화면이 "확인 필요"로 표기하게 한다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/application/test_rank_areas.py`:

```python
import pytest

from chika.application.usecase.rank_areas import RankAreas
from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed


def _station(station_id: str, ward: str = "中野区") -> Station:
    return Station(
        id=station_id,
        name_ja=station_id,
        name_ko=station_id,
        ward=ward,
        lat=35.70,
        lon=139.66,
        lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _usecase(
    stations: list[Station],
    raws: list[RawMetrics],
    commute: dict[tuple[str, str], int] | None = None,
    prices: dict[str, int] | None = None,
) -> RankAreas:
    return RankAreas(
        areas=FakeAreaMetricsRepository(stations, raws),
        commute=FakeCommuteRepository(commute or {}),
        prices=FakePriceRepository(prices or {}),
    )


def test_ranks_by_the_requested_dial() -> None:
    usecase = _usecase(
        [_station("kimchi"), _station("plain")],
        [_raw("kimchi", korean_restaurant=30.0), _raw("plain", korean_restaurant=0.0)],
    )
    result = usecase.execute(SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 1.0})))
    assert result[0].station.id == "kimchi"


def test_limit_caps_the_result_size() -> None:
    stations, raws, commute, prices = build_seed(count=40)
    result = _usecase(stations, raws, commute, prices).execute(
        SearchCriteria(dials=DialSettings.balanced()), limit=5
    )
    assert len(result) == 5


def test_excluded_ward_is_removed() -> None:
    usecase = _usecase(
        [_station("a", ward="新宿区"), _station("b", ward="中野区")],
        [_raw("a"), _raw("b")],
    )
    result = usecase.execute(
        SearchCriteria(dials=DialSettings.balanced(), exclude_wards=("新宿区",)), limit=10
    )
    assert [r.station.id for r in result] == ["b"]


def test_budget_filter_drops_stations_over_the_ceiling() -> None:
    usecase = _usecase(
        [_station("cheap"), _station("pricey")],
        [_raw("cheap"), _raw("pricey")],
        prices={"cheap": 100_000, "pricey": 300_000},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(),
            budget_yen=(0, 150_000),
            household=Household.SINGLE,
        ),
        limit=10,
    )
    assert [r.station.id for r in result] == ["cheap"]


def test_budget_filter_uses_household_adjusted_rent() -> None:
    usecase = _usecase(
        [_station("a")],
        [_raw("a")],
        prices={"a": 100_000},
    )
    criteria = SearchCriteria(dials=DialSettings.balanced(), budget_yen=(0, 150_000))
    assert len(usecase.execute(criteria, limit=10)) == 1
    family = criteria.replace(household=Household.FAMILY)  # 100_000 * 1.9 = 190_000
    assert usecase.execute(family, limit=10) == []


def test_commute_filter_drops_stations_over_the_limit() -> None:
    usecase = _usecase(
        [_station("near"), _station("far"), _station("hub")],
        [_raw("near"), _raw("far"), _raw("hub")],
        commute={("near", "hub"): 10, ("far", "hub"): 55},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(), commute_to="hub", commute_max_minutes=30
        ),
        limit=10,
    )
    assert {r.station.id for r in result} == {"near", "hub"}


def test_unknown_commute_is_kept_and_surfaced_as_none() -> None:
    usecase = _usecase(
        [_station("mystery"), _station("hub")],
        [_raw("mystery"), _raw("hub")],
        commute={},
    )
    result = usecase.execute(
        SearchCriteria(
            dials=DialSettings.balanced(), commute_to="hub", commute_max_minutes=30
        ),
        limit=10,
    )
    by_id = {r.station.id: r for r in result}
    assert "mystery" in by_id
    assert by_id["mystery"].commute_minutes is None


def test_percentiles_are_computed_before_filtering() -> None:
    """예산 필터를 걸어도 남은 역의 점수는 전체 모집단 기준 그대로여야 한다."""
    stations = [_station("a"), _station("b"), _station("c")]
    raws = [_raw("a", cafe=1.0), _raw("b", cafe=50.0), _raw("c", cafe=99.0)]
    prices = {"a": 100_000, "b": 100_000, "c": 300_000}
    criteria = SearchCriteria(dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0}))

    unfiltered = {r.station.id: r.score.total for r in _usecase(stations, raws, prices=prices).execute(criteria, limit=10)}
    filtered = {
        r.station.id: r.score.total
        for r in _usecase(stations, raws, prices=prices).execute(
            criteria.replace(budget_yen=(0, 150_000)), limit=10
        )
    }
    assert set(filtered) == {"a", "b"}
    assert filtered["a"] == pytest.approx(unfiltered["a"])
    assert filtered["b"] == pytest.approx(unfiltered["b"])


def test_result_carries_rent_and_commute_for_display() -> None:
    usecase = _usecase(
        [_station("a"), _station("hub")],
        [_raw("a"), _raw("hub")],
        commute={("a", "hub"): 22},
        prices={"a": 120_000},
    )
    result = usecase.execute(
        SearchCriteria(dials=DialSettings.balanced(), commute_to="hub"), limit=10
    )
    row = next(r for r in result if r.station.id == "a")
    assert row.rent_yen == 120_000
    assert row.commute_minutes == 22


def test_ranking_is_deterministic_across_runs() -> None:
    stations, raws, commute, prices = build_seed(count=40)
    criteria = SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 2.0, Dial.COST_RISK: 1.0}))
    first = [r.station.id for r in _usecase(stations, raws, commute, prices).execute(criteria)]
    second = [r.station.id for r in _usecase(stations, raws, commute, prices).execute(criteria)]
    assert first == second
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/application -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.rank_areas'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/application/usecase/rank_areas.py`:

```python
"""역세권 랭킹 유스케이스 (스펙 §2.1)."""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.score import AreaScore
from chika.domain.model.station import Station
from chika.domain.repository import (
    AreaMetricsRepository,
    CommuteRepository,
    PriceRepository,
)
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import rank


@dataclass(frozen=True)
class RankedArea:
    station: Station
    score: AreaScore
    rent_yen: int | None
    commute_minutes: int | None


class RankAreas:
    def __init__(
        self,
        areas: AreaMetricsRepository,
        commute: CommuteRepository,
        prices: PriceRepository,
    ) -> None:
        self._areas = areas
        self._commute = commute
        self._prices = prices

    def execute(self, criteria: SearchCriteria, limit: int = 5) -> list[RankedArea]:
        stations = {station.id: station for station in self._areas.stations()}
        # 퍼센타일은 필터 이전, 전체 모집단 기준으로 계산한다 (스펙 §6.3).
        scores = rank(normalize(self._areas.raw_metrics()), expand_dials(criteria.dials))

        results: list[RankedArea] = []
        for area_score in scores:
            station = stations.get(area_score.station_id)
            if station is None:
                continue
            if station.ward in criteria.exclude_wards:
                continue

            rent = self._prices.median_rent_yen(station.id, criteria.household)
            if not _within_budget(rent, criteria):
                continue

            minutes = (
                self._commute.minutes_to(station.id, criteria.commute_to)
                if criteria.commute_to is not None
                else None
            )
            if not _within_commute(minutes, criteria):
                continue

            results.append(
                RankedArea(
                    station=station,
                    score=area_score,
                    rent_yen=rent,
                    commute_minutes=minutes,
                )
            )
            if len(results) >= limit:
                break
        return results


def _within_budget(rent: int | None, criteria: SearchCriteria) -> bool:
    """시세를 모르면 통과시킨다 — 데이터 부재를 탈락으로 바꾸지 않는다."""
    if criteria.budget_yen is None or rent is None:
        return True
    low, high = criteria.budget_yen
    return low <= rent <= high


def _within_commute(minutes: int | None, criteria: SearchCriteria) -> bool:
    """통근 시간을 모르면 통과시키고 화면에서 '확인 필요'로 표기하게 한다."""
    if criteria.commute_max_minutes is None or minutes is None:
        return True
    return minutes <= criteria.commute_max_minutes
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run mypy src`
Expected: 63 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/application backend/tests/application
git commit -m "feat: RankAreas 유스케이스와 하드 필터"
```

---

### Task 9: ExplainArea / CompareAreas 유스케이스

**Files:**
- Create: `backend/src/chika/application/usecase/explain_area.py`
- Create: `backend/src/chika/application/usecase/compare_areas.py`
- Test: `backend/tests/application/test_explain_area.py`
- Test: `backend/tests/application/test_compare_areas.py`

**Interfaces:**
- Consumes: Task 8의 `RankAreas` 구성요소와 동일한 포트들
- Produces:
  - `MetricDetail(key: MetricKey, percentile: float, contribution: float, is_missing: bool, is_ward_resolution: bool)`
  - `AreaExplanation(station: Station, total: float, rent_yen: int | None, strengths: list[MetricDetail], weaknesses: list[MetricDetail], missing: list[MetricKey])`
  - `ExplainArea(areas, prices)` — `.execute(station_id: str, criteria: SearchCriteria, top_n: int = 3) -> AreaExplanation`
  - `MetricDifference(key: MetricKey, percentiles: dict[str, float], spread: float)`
  - `AreaComparison(stations: list[Station], totals: dict[str, float], differences: list[MetricDifference])`
  - `CompareAreas(areas)` — `.execute(station_ids: Sequence[str], criteria: SearchCriteria, top_n: int = 5) -> AreaComparison`

**설계 메모:** 두 유스케이스 모두 **LLM에 넘길 재료만 만든다**. 문장은 만들지 않는다. `is_ward_resolution` 은 스펙 §3.2가 요구하는 "구 단위입니다" 표기를 화면까지 실어 나르는 통로다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/application/test_explain_area.py`:

```python
import pytest

from chika.application.usecase.explain_area import ExplainArea
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import Dial, DialSettings
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository, FakePriceRepository


def _station(station_id: str) -> Station:
    return Station(
        id=station_id, name_ja=station_id, name_ko=station_id,
        ward="中野区", lat=35.70, lon=139.66, lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _usecase(stations: list[Station], raws: list[RawMetrics], prices: dict[str, int]) -> ExplainArea:
    return ExplainArea(
        areas=FakeAreaMetricsRepository(stations, raws),
        prices=FakePriceRepository(prices),
    )


def test_strengths_are_the_top_positive_contributions() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", korean_restaurant=99.0, park=0.0), _raw("b", korean_restaurant=0.0, park=99.0)],
        {"a": 120_000},
    )
    criteria = SearchCriteria(
        dials=DialSettings({Dial.KOREAN_LIFE: 1.0, Dial.QUALITY_OF_LIFE: 1.0})
    )
    result = usecase.execute("a", criteria)
    assert result.strengths[0].key is MetricKey.KOREAN_RESTAURANT
    assert result.strengths[0].contribution > 0
    assert result.weaknesses[0].key is MetricKey.PARK


def test_ward_resolution_flag_is_surfaced() -> None:
    # 역이 하나뿐이면 모든 기여도가 0이라 특정 지표가 상위 3개에 든다는 보장이 없다.
    # 구 단위 지표에 실제 편차를 만들어 strengths에 올라오게 한다.
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", korean_resident_ratio=0.04), _raw("b", korean_resident_ratio=0.001)],
        {},
    )
    result = usecase.execute("a", SearchCriteria(dials=DialSettings({Dial.KOREAN_LIFE: 1.0})))
    ratio = next(d for d in result.strengths if d.key is MetricKey.KOREAN_RESIDENT_RATIO)
    assert ratio.is_ward_resolution is True


def test_missing_metrics_are_listed() -> None:
    usecase = _usecase([_station("a")], [_raw("a", korean_grocery=None)], {})
    result = usecase.execute("a", SearchCriteria(dials=DialSettings.balanced()))
    assert MetricKey.KOREAN_GROCERY in result.missing


def test_total_matches_the_ranking_score() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", cafe=99.0), _raw("b", cafe=1.0)],
        {},
    )
    result = usecase.execute("a", SearchCriteria(dials=DialSettings({Dial.QUALITY_OF_LIFE: 1.0})))
    assert result.total > 50.0


def test_rent_is_included_when_known() -> None:
    usecase = _usecase([_station("a")], [_raw("a")], {"a": 133_000})
    result = usecase.execute("a", SearchCriteria(dials=DialSettings.balanced()))
    assert result.rent_yen == 133_000


def test_unknown_station_raises() -> None:
    usecase = _usecase([_station("a")], [_raw("a")], {})
    with pytest.raises(KeyError, match="zzz"):
        usecase.execute("zzz", SearchCriteria(dials=DialSettings.balanced()))
```

`backend/tests/application/test_compare_areas.py`:

```python
import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station
from chika.domain.model.weights import DialSettings
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


def _station(station_id: str) -> Station:
    return Station(
        id=station_id, name_ja=station_id, name_ko=station_id,
        ward="中野区", lat=35.70, lon=139.66, lines=(),
    )


def _raw(station_id: str, **values: float | None) -> RawMetrics:
    filled: dict[MetricKey, float | None] = {key: 1.0 for key in MetricKey}
    for name, value in values.items():
        filled[MetricKey(name)] = value
    return RawMetrics(station_id=station_id, values=filled)


def _usecase(stations: list[Station], raws: list[RawMetrics]) -> CompareAreas:
    return CompareAreas(areas=FakeAreaMetricsRepository(stations, raws))


def test_only_differing_axes_are_returned_first() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [
            _raw("a", cafe=99.0, supermarket=5.0),
            _raw("b", cafe=1.0, supermarket=5.0),
        ],
    )
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()), top_n=1)
    assert result.differences[0].key is MetricKey.CAFE


def test_identical_areas_have_zero_spread() -> None:
    usecase = _usecase([_station("a"), _station("b")], [_raw("a"), _raw("b")])
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()))
    assert all(diff.spread == pytest.approx(0.0) for diff in result.differences)


def test_percentiles_are_reported_per_station() -> None:
    usecase = _usecase(
        [_station("a"), _station("b")],
        [_raw("a", cafe=99.0), _raw("b", cafe=1.0)],
    )
    result = usecase.execute(["a", "b"], SearchCriteria(dials=DialSettings.balanced()), top_n=1)
    diff = result.differences[0]
    assert set(diff.percentiles) == {"a", "b"}
    assert diff.percentiles["a"] > diff.percentiles["b"]


def test_totals_are_returned_for_every_station() -> None:
    usecase = _usecase(
        [_station("a"), _station("b"), _station("c")],
        [_raw("a", cafe=99.0), _raw("b", cafe=50.0), _raw("c", cafe=1.0)],
    )
    result = usecase.execute(["a", "c"], SearchCriteria(dials=DialSettings.balanced()))
    assert set(result.totals) == {"a", "c"}


def test_comparing_fewer_than_two_stations_is_rejected() -> None:
    usecase = _usecase([_station("a")], [_raw("a")])
    with pytest.raises(ValueError, match="at least two"):
        usecase.execute(["a"], SearchCriteria(dials=DialSettings.balanced()))


def test_unknown_station_raises() -> None:
    usecase = _usecase([_station("a"), _station("b")], [_raw("a"), _raw("b")])
    with pytest.raises(KeyError, match="zzz"):
        usecase.execute(["a", "zzz"], SearchCriteria(dials=DialSettings.balanced()))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/application -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.application.usecase.explain_area'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/application/usecase/explain_area.py`:

```python
"""지표 기여도 분해 (스펙 §2.1 '왜 여기가 1위인가').

LLM에 넘길 재료만 만든다. 문장은 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import WARD_RESOLUTION_METRICS, AreaMetrics, MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository, PriceRepository
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDetail:
    key: MetricKey
    percentile: float
    contribution: float
    is_missing: bool
    is_ward_resolution: bool


@dataclass(frozen=True)
class AreaExplanation:
    station: Station
    total: float
    rent_yen: int | None
    strengths: list[MetricDetail]
    weaknesses: list[MetricDetail]
    missing: list[MetricKey]


class ExplainArea:
    def __init__(self, areas: AreaMetricsRepository, prices: PriceRepository) -> None:
        self._areas = areas
        self._prices = prices

    def execute(
        self, station_id: str, criteria: SearchCriteria, top_n: int = 3
    ) -> AreaExplanation:
        station = next((s for s in self._areas.stations() if s.id == station_id), None)
        if station is None:
            raise KeyError(f"unknown station: {station_id}")

        area = _find_area(normalize(self._areas.raw_metrics()), station_id)
        area_score = score(area, expand_dials(criteria.dials))

        def detail(key: MetricKey) -> MetricDetail:
            return MetricDetail(
                key=key,
                percentile=area.percentile[key],
                contribution=area_score.contributions[key],
                is_missing=key in area.missing,
                is_ward_resolution=key in WARD_RESOLUTION_METRICS,
            )

        return AreaExplanation(
            station=station,
            total=area_score.total,
            rent_yen=self._prices.median_rent_yen(station_id, criteria.household),
            strengths=[detail(key) for key, _ in area_score.top_drivers(top_n)],
            weaknesses=[detail(key) for key, _ in area_score.bottom_drivers(top_n)],
            missing=sorted(area.missing),
        )


def _find_area(areas: list[AreaMetrics], station_id: str) -> AreaMetrics:
    for area in areas:
        if area.station_id == station_id:
            return area
    raise KeyError(f"unknown station: {station_id}")
```

`backend/src/chika/application/usecase/compare_areas.py`:

```python
"""후보지 비교 (스펙 §2.2-1). 차이 나는 축만 위로 올린다."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chika.domain.model.criteria import SearchCriteria
from chika.domain.model.metrics import MetricKey
from chika.domain.model.station import Station
from chika.domain.repository import AreaMetricsRepository
from chika.domain.service.dials import expand_dials
from chika.domain.service.normalization import normalize
from chika.domain.service.scoring import score


@dataclass(frozen=True)
class MetricDifference:
    key: MetricKey
    percentiles: dict[str, float]
    spread: float


@dataclass(frozen=True)
class AreaComparison:
    stations: list[Station]
    totals: dict[str, float]
    differences: list[MetricDifference]


class CompareAreas:
    def __init__(self, areas: AreaMetricsRepository) -> None:
        self._areas = areas

    def execute(
        self,
        station_ids: Sequence[str],
        criteria: SearchCriteria,
        top_n: int = 5,
    ) -> AreaComparison:
        if len(station_ids) < 2:
            raise ValueError("compare needs at least two stations")

        by_id = {station.id: station for station in self._areas.stations()}
        stations = []
        for station_id in station_ids:
            if station_id not in by_id:
                raise KeyError(f"unknown station: {station_id}")
            stations.append(by_id[station_id])

        areas = {area.station_id: area for area in normalize(self._areas.raw_metrics())}
        weights = expand_dials(criteria.dials)

        totals = {sid: score(areas[sid], weights).total for sid in station_ids}

        differences = []
        for key in MetricKey:
            percentiles = {sid: areas[sid].percentile[key] for sid in station_ids}
            values = list(percentiles.values())
            differences.append(
                MetricDifference(
                    key=key,
                    percentiles=percentiles,
                    spread=max(values) - min(values),
                )
            )
        differences.sort(key=lambda diff: (-diff.spread, diff.key.value))

        return AreaComparison(
            stations=stations,
            totals=totals,
            differences=differences[:top_n],
        )
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run mypy src`
Expected: 75 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/application backend/tests/application
git commit -m "feat: ExplainArea / CompareAreas 유스케이스"
```

---

### Task 10: 역 마스터 ETL (국토수치정보)

**Files:**
- Create: `backend/src/chika/etl/station_master.py`
- Create: `backend/src/chika/etl/build_stations.py`
- Create: `backend/data/station_name_ko.json`
- Create: `backend/src/chika/infrastructure/station_file.py`
- Test: `backend/tests/etl/test_station_master.py`
- Test: `backend/tests/infrastructure/test_station_file.py`

**Interfaces:**
- Consumes: `Station` (Task 2), `AreaMetricsRepository` 포트 (Task 6)
- Produces:
  - `slugify_station(name_ja: str) -> str`
  - `parse_ward_polygons(n03_geojson: dict) -> list[tuple[str, list[tuple[float, float]]]]` — (구 이름, 외곽 링)
  - `parse_stations(n02_geojson: dict, wards, name_ko: Mapping[str, str]) -> list[Station]`
  - `StationFileRepository(path: Path)` — `stations()` 만 구현하고 `raw_metrics()` 는 빈 목록. Phase 2에서 BigQuery 어댑터가 지표를 채운다.
  - CLI: `uv run python -m chika.etl.build_stations --n02 <path> --n03 <path> --out data/stations.json`

**설계 메모:** 국토수치정보는 로그인 없이 내려받는 ZIP이지만 **연도별 파일명이 자주 바뀐다.** 그래서 다운로드는 수동 단계로 두고, 코드는 이미 로컬에 있는 GeoJSON만 다룬다. 덕분에 테스트는 인라인 픽스처로 네트워크 없이 돌아간다.

`ST_WITHIN` 대신 순수 파이썬 ray-casting 을 쓴다. shapely 를 ETL 전용 optional dependency 로 두었지만, 구 폴리곤 판정 정도는 의존성 없이 충분하고 도메인 규칙(외부 의존 최소화)과도 맞는다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/etl/test_station_master.py`:

```python
import pytest

from chika.etl.station_master import parse_stations, parse_ward_polygons, slugify_station

# 中野区 대용의 정사각형 폴리곤. 실제 좌표계(WGS84)와 같은 단위를 쓴다.
_N03 = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {"N03_001": "東京都", "N03_004": "中野区"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[139.60, 35.68], [139.72, 35.68], [139.72, 35.74], [139.60, 35.74], [139.60, 35.68]]],
            },
        },
        {
            "properties": {"N03_001": "神奈川県", "N03_004": "横浜市"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[139.60, 35.40], [139.72, 35.40], [139.72, 35.46], [139.60, 35.46], [139.60, 35.40]]],
            },
        },
    ],
}


def _station_feature(name: str, line: str, lon: float, lat: float) -> dict:
    """N02의 역 피처는 LineString(플랫폼 선)이다. 중점을 대표 좌표로 쓴다."""
    return {
        "properties": {"N02_003": line, "N02_004": "東日本旅客鉄道", "N02_005": name},
        "geometry": {"type": "LineString", "coordinates": [[lon - 0.001, lat], [lon + 0.001, lat]]},
    }


def test_slugify_uses_ascii_and_is_stable() -> None:
    assert slugify_station("中野") == slugify_station("中野")
    assert slugify_station("中野").isascii()
    assert slugify_station("中野") != slugify_station("新宿")


def test_parse_ward_polygons_keeps_only_tokyo() -> None:
    wards = parse_ward_polygons(_N03)
    assert [name for name, _ in wards] == ["中野区"]


def test_station_inside_a_ward_is_kept_with_its_ward_name() -> None:
    n02 = {"type": "FeatureCollection", "features": [_station_feature("中野", "中央線", 139.66, 35.70)]}
    stations = parse_stations(n02, parse_ward_polygons(_N03), {"中野": "나카노"})
    assert len(stations) == 1
    assert stations[0].ward == "中野区"
    assert stations[0].name_ko == "나카노"
    assert stations[0].lon == pytest.approx(139.66)


def test_station_outside_the_23_wards_is_dropped() -> None:
    n02 = {"type": "FeatureCollection", "features": [_station_feature("横浜", "東海道線", 139.66, 35.43)]}
    assert parse_stations(n02, parse_ward_polygons(_N03), {}) == []


def test_same_station_on_multiple_lines_is_merged() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [
            _station_feature("中野", "中央線", 139.66, 35.70),
            _station_feature("中野", "東西線", 139.661, 35.701),
        ],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert len(stations) == 1
    assert set(stations[0].lines) == {"中央線", "東西線"}


def test_korean_name_falls_back_to_japanese_when_unmapped() -> None:
    n02 = {"type": "FeatureCollection", "features": [_station_feature("中野", "中央線", 139.66, 35.70)]}
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert stations[0].name_ko == "中野"


def test_output_is_sorted_by_id_for_deterministic_diffs() -> None:
    n02 = {
        "type": "FeatureCollection",
        "features": [
            _station_feature("中野", "中央線", 139.66, 35.70),
            _station_feature("新宿", "山手線", 139.70, 35.69),
        ],
    }
    stations = parse_stations(n02, parse_ward_polygons(_N03), {})
    assert [s.id for s in stations] == sorted(s.id for s in stations)
```

`backend/tests/infrastructure/test_station_file.py`:

```python
import json
from pathlib import Path

import pytest

from chika.infrastructure.station_file import StationFileRepository


def _write(tmp_path: Path, payload: list[dict]) -> Path:
    path = tmp_path / "stations.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_loads_stations_from_json(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "id": "nakano",
                "name_ja": "中野",
                "name_ko": "나카노",
                "ward": "中野区",
                "lat": 35.7056,
                "lon": 139.6659,
                "lines": ["中央線"],
            }
        ],
    )
    repo = StationFileRepository(path)
    stations = repo.stations()
    assert len(stations) == 1
    assert stations[0].name_ko == "나카노"
    assert stations[0].lines == ("中央線",)


def test_raw_metrics_is_empty_until_phase_2(tmp_path: Path) -> None:
    repo = StationFileRepository(_write(tmp_path, []))
    assert list(repo.raw_metrics()) == []


def test_missing_file_raises_a_clear_error(tmp_path: Path) -> None:
    repo = StationFileRepository(tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="nope.json"):
        repo.stations()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/etl tests/infrastructure/test_station_file.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.station_master'`

- [ ] **Step 3: 최소 구현**

`backend/src/chika/etl/station_master.py`:

```python
"""국토수치정보(N02 철도 / N03 행정구역) → 역 마스터.

다운로드는 수동이다. 연도별 파일명이 자주 바뀌어 URL을 코드에 박으면 금방 썩는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence

from chika.domain.model.station import Station

Ring = list[tuple[float, float]]
Ward = tuple[str, Ring]

TOKYO_PREFECTURE = "東京都"


def slugify_station(name_ja: str) -> str:
    """일본어 역명을 안정적인 ASCII id로 바꾼다.

    로마자 변환기를 의존성으로 들이는 대신 해시를 쓴다. id는 사람이 읽는 값이
    아니라 참조 키이고, 화면에는 name_ja/name_ko가 나간다.
    """
    digest = hashlib.sha1(name_ja.encode("utf-8")).hexdigest()
    return f"st_{digest[:12]}"


def parse_ward_polygons(n03_geojson: Mapping[str, object]) -> list[Ward]:
    """도쿄도 시구정촌 폴리곤만 뽑는다. 멀티폴리곤은 링 단위로 펼친다."""
    wards: list[Ward] = []
    for feature in _features(n03_geojson):
        props = feature.get("properties") or {}
        if props.get("N03_001") != TOKYO_PREFECTURE:
            continue
        name = props.get("N03_004")
        if not isinstance(name, str):
            continue
        for ring in _outer_rings(feature.get("geometry") or {}):
            wards.append((name, ring))
    return wards


def parse_stations(
    n02_geojson: Mapping[str, object],
    wards: Sequence[Ward],
    name_ko: Mapping[str, str],
) -> list[Station]:
    """N02 역 피처를 역명 기준으로 병합해 Station 목록을 만든다.

    같은 역명이 노선 수만큼 반복되므로 첫 좌표를 대표로 쓰고 노선만 합친다.
    """
    merged: dict[str, dict[str, object]] = {}

    for feature in _features(n02_geojson):
        props = feature.get("properties") or {}
        name = props.get("N02_005")
        line = props.get("N02_003")
        if not isinstance(name, str) or not isinstance(line, str):
            continue

        point = _representative_point(feature.get("geometry") or {})
        if point is None:
            continue
        lon, lat = point

        ward = _ward_containing(lon, lat, wards)
        if ward is None:
            continue  # 23구 밖

        station_id = slugify_station(name)
        entry = merged.setdefault(
            station_id,
            {"name_ja": name, "ward": ward, "lat": lat, "lon": lon, "lines": []},
        )
        lines = entry["lines"]
        assert isinstance(lines, list)
        if line not in lines:
            lines.append(line)

    stations = [
        Station(
            id=station_id,
            name_ja=str(entry["name_ja"]),
            name_ko=name_ko.get(str(entry["name_ja"]), str(entry["name_ja"])),
            ward=str(entry["ward"]),
            lat=float(entry["lat"]),  # type: ignore[arg-type]
            lon=float(entry["lon"]),  # type: ignore[arg-type]
            lines=tuple(sorted(entry["lines"])),  # type: ignore[arg-type]
        )
        for station_id, entry in merged.items()
    ]
    return sorted(stations, key=lambda s: s.id)


def _features(geojson: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    features = geojson.get("features")
    if not isinstance(features, list):
        return []
    return [f for f in features if isinstance(f, dict)]


def _outer_rings(geometry: Mapping[str, object]) -> list[Ring]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Polygon" and isinstance(coords, list) and coords:
        return [[(float(p[0]), float(p[1])) for p in coords[0]]]
    if kind == "MultiPolygon" and isinstance(coords, list):
        return [[(float(p[0]), float(p[1])) for p in polygon[0]] for polygon in coords if polygon]
    return []


def _representative_point(geometry: Mapping[str, object]) -> tuple[float, float] | None:
    """N02 역은 LineString(플랫폼 선)이다. 중점을 역 좌표로 삼는다."""
    coords = geometry.get("coordinates")
    kind = geometry.get("type")
    if kind == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    if kind == "LineString" and isinstance(coords, list) and coords:
        lons = [float(p[0]) for p in coords]
        lats = [float(p[1]) for p in coords]
        return sum(lons) / len(lons), sum(lats) / len(lats)
    return None


def _ward_containing(lon: float, lat: float, wards: Sequence[Ward]) -> str | None:
    for name, ring in wards:
        if _point_in_ring(lon, lat, ring):
            return name
    return None


def _point_in_ring(lon: float, lat: float, ring: Ring) -> bool:
    """ray casting. 구 경계 판정에는 이걸로 충분하다."""
    inside = False
    count = len(ring)
    for i in range(count):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % count]
        if (y1 > lat) != (y2 > lat):
            x_at_lat = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_at_lat:
                inside = not inside
    return inside
```

`backend/src/chika/etl/build_stations.py`:

```python
"""역 마스터 생성 CLI.

사전 준비 (수동):
  1. https://nlftp.mlit.go.jp/ksj/ 에서 N02(鉄道) 최신 연도판 GeoJSON을 받는다.
  2. 같은 사이트에서 N03(行政区域) 東京都 GeoJSON을 받는다.
  3. 두 파일 경로를 아래 인자로 넘긴다.

  uv run python -m chika.etl.build_stations \\
      --n02 ~/Downloads/N02.geojson \\
      --n03 ~/Downloads/N03-tokyo.geojson \\
      --out data/stations.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from chika.etl.station_master import parse_stations, parse_ward_polygons

#: 도쿄 23구. N03에는 시·정·촌도 섞여 있으므로 여기서 걸러낸다.
TOKYO_23_WARDS: frozenset[str] = frozenset(
    {
        "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区",
        "墨田区", "江東区", "品川区", "目黒区", "大田区", "世田谷区",
        "渋谷区", "中野区", "杉並区", "豊島区", "北区", "荒川区",
        "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区",
    }
)


def main() -> None:
    parser = argparse.ArgumentParser(description="국토수치정보에서 역 마스터를 만든다")
    parser.add_argument("--n02", type=Path, required=True, help="N02 철도 GeoJSON")
    parser.add_argument("--n03", type=Path, required=True, help="N03 행정구역 GeoJSON")
    parser.add_argument("--name-ko", type=Path, default=Path("data/station_name_ko.json"))
    parser.add_argument("--out", type=Path, default=Path("data/stations.json"))
    args = parser.parse_args()

    n02 = json.loads(args.n02.read_text(encoding="utf-8"))
    n03 = json.loads(args.n03.read_text(encoding="utf-8"))
    name_ko = json.loads(args.name_ko.read_text(encoding="utf-8")) if args.name_ko.exists() else {}

    wards = [(name, ring) for name, ring in parse_ward_polygons(n03) if name in TOKYO_23_WARDS]
    stations = parse_stations(n02, wards, name_ko)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([dataclasses.asdict(s) for s in stations], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(stations)} stations -> {args.out}")


if __name__ == "__main__":
    main()
```

`backend/data/station_name_ko.json` (초기 시드. 나머지는 name_ja 로 폴백된다):

```json
{
  "新宿": "신주쿠",
  "渋谷": "시부야",
  "池袋": "이케부쿠로",
  "東京": "도쿄",
  "品川": "시나가와",
  "上野": "우에노",
  "中野": "나카노",
  "高円寺": "고엔지",
  "吉祥寺": "기치조지",
  "大久保": "오쿠보",
  "新大久保": "신오쿠보",
  "赤坂": "아카사카",
  "六本木": "롯폰기",
  "恵比寿": "에비스",
  "目黒": "메구로",
  "五反田": "고탄다",
  "秋葉原": "아키하바라",
  "北千住": "기타센주",
  "錦糸町": "긴시초",
  "門前仲町": "몬젠나카초"
}
```

`backend/src/chika/infrastructure/station_file.py`:

```python
"""역 마스터 JSON 파일 어댑터. Phase 2에서 BigQuery 어댑터가 지표를 채운다."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station


class StationFileRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def stations(self) -> Sequence[Station]:
        if not self._path.exists():
            raise FileNotFoundError(f"station master not found: {self._path}")
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            Station(
                id=row["id"],
                name_ja=row["name_ja"],
                name_ko=row["name_ko"],
                ward=row["ward"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                lines=tuple(row["lines"]),
            )
            for row in payload
        ]

    def raw_metrics(self) -> Sequence[RawMetrics]:
        """Phase 0에서는 지표가 없다. Phase 2의 BigQuery 어댑터가 채운다."""
        return []
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run mypy src`
Expected: 85 passed

- [ ] **Step 5: 실제 데이터로 한 번 돌려 검증한다**

N02/N03 GeoJSON을 받아 CLI를 실행하고 결과를 확인한다:

```bash
cd backend && uv run python -m chika.etl.build_stations --n02 <N02경로> --n03 <N03경로> --out data/stations.json
```

Expected: `약 200~350 stations -> data/stations.json`. 스펙의 "약 250개"와 자릿수가 맞아야 한다.
0개거나 1000개가 넘으면 N03 필터링(`TOKYO_23_WARDS`)이나 좌표 순서(lon, lat)를 먼저 의심한다.

`data/stations.json` 은 산출물이므로 `backend/.gitignore` 에 추가하고 커밋하지 않는다:

```bash
printf 'data/stations.json\n' >> backend/.gitignore
```

- [ ] **Step 6: 커밋**

```bash
git add backend/src/chika/etl backend/src/chika/infrastructure/station_file.py \
        backend/data/station_name_ko.json backend/tests/etl \
        backend/tests/infrastructure/test_station_file.py backend/.gitignore
git commit -m "feat: 국토수치정보 기반 역 마스터 ETL"
```

---

### Task 11: 에이전트 골격 (IntakeAgent + AnalysisAgent)

**Files:**
- Create: `backend/src/chika/interface/agent/__init__.py`
- Create: `backend/src/chika/interface/agent/state.py`
- Create: `backend/src/chika/interface/agent/actions.py`
- Create: `backend/src/chika/interface/agent/tools.py`
- Create: `backend/src/chika/interface/agent/agents.py`
- Test: `backend/tests/interface/test_agent_actions.py`
- Test: `backend/tests/interface/test_agent_wiring.py`

**Interfaces:**
- Consumes: `RankAreas`/`RankedArea` (Task 8), `ExplainArea`/`AreaExplanation`, `CompareAreas`/`AreaComparison` (Task 9), `SearchCriteria`/`Household` (Task 6), `Dial`/`DialSettings` (Task 3)
- Produces:
  - `UseCases(rank: RankAreas, explain: ExplainArea, compare: CompareAreas)`
  - `SessionState(usecases: UseCases, criteria: SearchCriteria | None = None, last_ranking: list[RankedArea] = [])`
  - 순수 액션 함수 (LLM 없이 테스트 가능):
    - `act_set_criteria(state, korean_life, daily_convenience, quality_of_life, family, cost_risk, commute_to, commute_max_minutes, budget_min_yen, budget_max_yen, household, exclude_wards) -> dict`
    - `act_rank_areas(state, limit=5) -> dict`
    - `act_explain_area(state, station_id) -> dict`
    - `act_compare_areas(state, station_ids) -> dict`
  - `VALUE_GAP_DISCLAIMER: str`
  - `build_agents(state: SessionState) -> Agent` — IntakeAgent를 반환하고, 여기서 AnalysisAgent로 핸드오프한다

**설계 메모:** `function_tool` 데코레이터가 붙은 객체는 직접 호출해 테스트하기 번거롭다. 그래서 **로직은 전부 `actions.py` 의 평범한 함수**에 두고 `tools.py` 는 데코레이터로 감싸기만 한다. 덕분에 에이전트 로직의 거의 전부가 LLM·네트워크 없이 단위 테스트된다.

가드레일(스펙 §5.3)은 액션 함수 안에 둔다. 프롬프트에만 적어두면 지켜지지 않는다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/interface/test_agent_actions.py`:

```python
import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.domain.model.criteria import Household
from chika.domain.model.weights import Dial
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.actions import (
    act_compare_areas,
    act_explain_area,
    act_rank_areas,
    act_set_criteria,
)
from chika.interface.agent.state import SessionState, UseCases


@pytest.fixture
def state() -> SessionState:
    stations, raws, commute, prices = build_seed(count=40)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
        )
    )


def _set_default_criteria(state: SessionState) -> dict:
    return act_set_criteria(
        state,
        korean_life=3.0,
        daily_convenience=2.0,
        quality_of_life=1.0,
        family=0.0,
        cost_risk=2.0,
    )


def test_set_criteria_stores_dials_on_the_session(state: SessionState) -> None:
    _set_default_criteria(state)
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.KOREAN_LIFE) == 3.0
    assert state.criteria.dials.strength(Dial.FAMILY) == 0.0


def test_set_criteria_returns_the_expanded_weights_for_transparency(state: SessionState) -> None:
    result = _set_default_criteria(state)
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert result["weights"]["korean_restaurant"] > result["weights"]["cafe"]


def test_set_criteria_accepts_budget_and_household(state: SessionState) -> None:
    act_set_criteria(
        state,
        korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0, family=1.0, cost_risk=1.0,
        budget_min_yen=80_000, budget_max_yen=150_000, household="family",
    )
    assert state.criteria is not None
    assert state.criteria.budget_yen == (80_000, 150_000)
    assert state.criteria.household is Household.FAMILY


def test_set_criteria_rejects_an_unknown_household(state: SessionState) -> None:
    with pytest.raises(ValueError, match="household"):
        act_set_criteria(
            state,
            korean_life=1.0, daily_convenience=1.0, quality_of_life=1.0,
            family=1.0, cost_risk=1.0, household="dormitory",
        )


def test_set_criteria_can_be_called_again_to_revise(state: SessionState) -> None:
    _set_default_criteria(state)
    act_set_criteria(
        state,
        korean_life=0.0, daily_convenience=0.0, quality_of_life=0.0, family=5.0, cost_risk=0.0,
        budget_max_yen=120_000,
    )
    assert state.criteria is not None
    assert state.criteria.dials.strength(Dial.FAMILY) == 5.0
    assert state.criteria.budget_yen == (0, 120_000)


def test_rank_before_set_criteria_is_refused(state: SessionState) -> None:
    result = act_rank_areas(state)
    assert result["error"] == "criteria_not_set"
    assert result["areas"] == []


def test_rank_returns_scores_and_drivers(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_rank_areas(state, limit=3)
    assert len(result["areas"]) == 3
    first = result["areas"][0]
    assert set(first) >= {"station_id", "name_ko", "ward", "lat", "lon", "score", "top_drivers"}
    assert 0.0 <= first["score"] <= 100.0
    assert len(first["top_drivers"]) == 3


def test_rank_caps_the_limit_to_protect_the_context_window(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_rank_areas(state, limit=999)
    assert len(result["areas"]) <= 10


def test_rank_stores_the_result_for_follow_up_questions(state: SessionState) -> None:
    _set_default_criteria(state)
    act_rank_areas(state, limit=3)
    assert len(state.last_ranking) == 3


def test_explain_returns_strengths_weaknesses_and_ward_flag(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    station_id = ranked["areas"][0]["station_id"]
    result = act_explain_area(state, station_id)
    assert result["strengths"]
    assert result["weaknesses"]
    assert all("is_ward_resolution" in item for item in result["strengths"])


def test_explain_marks_ward_resolution_metrics(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=1)
    result = act_explain_area(state, ranked["areas"][0]["station_id"])
    details = result["strengths"] + result["weaknesses"]
    ratios = [d for d in details if d["metric"] == "korean_resident_ratio"]
    assert all(d["is_ward_resolution"] for d in ratios)


def test_explain_of_unknown_station_returns_an_error_not_an_exception(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_explain_area(state, "no_such_station")
    assert result["error"] == "unknown_station"


def test_compare_returns_only_the_differing_axes(state: SessionState) -> None:
    _set_default_criteria(state)
    ranked = act_rank_areas(state, limit=3)
    ids = [area["station_id"] for area in ranked["areas"][:2]]
    result = act_compare_areas(state, ids)
    assert len(result["differences"]) <= 5
    spreads = [d["spread"] for d in result["differences"]]
    assert spreads == sorted(spreads, reverse=True)


def test_compare_needs_two_stations(state: SessionState) -> None:
    _set_default_criteria(state)
    result = act_compare_areas(state, ["seed_000"])
    assert result["error"] == "need_two_stations"
```

`backend/tests/interface/test_agent_wiring.py`:

```python
"""에이전트 배선만 확인한다. LLM 호출은 하지 않는다."""

import pytest

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.state import SessionState, UseCases

pytest.importorskip("agents", reason="openai-agents 미설치 환경에서는 건너뛴다")

from chika.interface.agent.agents import build_agents  # noqa: E402


def _state() -> SessionState:
    stations, raws, commute, prices = build_seed(count=10)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
        )
    )


def test_entry_agent_is_intake_and_hands_off_to_analysis() -> None:
    intake = build_agents(_state())
    assert intake.name == "IntakeAgent"
    assert [h.name for h in intake.handoffs] == ["AnalysisAgent"]


def test_intake_owns_only_the_criteria_tool() -> None:
    intake = build_agents(_state())
    assert [t.name for t in intake.tools] == ["set_criteria"]


def test_analysis_agent_exposes_the_three_analysis_tools() -> None:
    analysis = build_agents(_state()).handoffs[0]
    assert set(t.name for t in analysis.tools) == {"rank_areas", "explain_area", "compare_areas"}


def test_instructions_carry_the_guardrails() -> None:
    intake = build_agents(_state())
    analysis = intake.handoffs[0]
    assert "23区" in intake.instructions or "23구" in intake.instructions
    assert "투자" in analysis.instructions
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv sync --extra agent && uv run pytest tests/interface -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.interface.agent'`

- [ ] **Step 3: 최소 구현**

```bash
mkdir -p backend/src/chika/interface/agent && touch backend/src/chika/interface/agent/__init__.py
```

`backend/src/chika/interface/agent/state.py`:

```python
"""대화 세션 상태. Agents SDK의 context로 전달된다 (스펙 §5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas, RankedArea
from chika.domain.model.criteria import SearchCriteria


@dataclass(frozen=True)
class UseCases:
    rank: RankAreas
    explain: ExplainArea
    compare: CompareAreas


@dataclass
class SessionState:
    usecases: UseCases
    criteria: SearchCriteria | None = None
    last_ranking: list[RankedArea] = field(default_factory=list)
```

`backend/src/chika/interface/agent/actions.py`:

```python
"""툴의 알맹이. LLM 없이 전부 단위 테스트된다.

가드레일은 프롬프트가 아니라 여기에 둔다 — 프롬프트에만 적으면 지켜지지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chika.domain.model.criteria import Household, SearchCriteria
from chika.domain.model.weights import Dial, DialSettings
from chika.domain.service.dials import expand_dials
from chika.interface.agent.state import SessionState

#: 한 번에 LLM에 넘기는 역의 상한. 컨텍스트 낭비와 서술 품질 저하를 막는다.
MAX_RANKING_LIMIT = 10

VALUE_GAP_DISCLAIMER = (
    "이 수치는 공개 데이터에 기반한 통계적 추정이며 투자 조언이 아닙니다. "
    "실제 계약 전에는 반드시 현장과 중개사를 통해 확인하세요."
)


def act_set_criteria(
    state: SessionState,
    korean_life: float,
    daily_convenience: float,
    quality_of_life: float,
    family: float,
    cost_risk: float,
    commute_to: str | None = None,
    commute_max_minutes: int | None = None,
    budget_min_yen: int | None = None,
    budget_max_yen: int | None = None,
    household: str = "single",
    exclude_wards: Sequence[str] = (),
) -> dict[str, Any]:
    """대화에서 모은 조건을 세션에 확정한다. 다시 불러 일부만 바꿔도 된다."""
    try:
        household_value = Household(household)
    except ValueError as exc:
        raise ValueError(
            f"unknown household: {household!r} (single/couple/family 중 하나)"
        ) from exc

    budget: tuple[int, int] | None = None
    if budget_min_yen is not None or budget_max_yen is not None:
        budget = (budget_min_yen or 0, budget_max_yen or 10_000_000)

    dials = DialSettings(
        {
            Dial.KOREAN_LIFE: korean_life,
            Dial.DAILY_CONVENIENCE: daily_convenience,
            Dial.QUALITY_OF_LIFE: quality_of_life,
            Dial.FAMILY: family,
            Dial.COST_RISK: cost_risk,
        }
    )
    criteria = SearchCriteria(
        dials=dials,
        commute_to=commute_to,
        commute_max_minutes=commute_max_minutes,
        budget_yen=budget,
        household=household_value,
        exclude_wards=tuple(exclude_wards),
    )
    state.criteria = criteria
    state.last_ranking = []

    weights = expand_dials(dials)
    return {
        "ok": True,
        "weights": {key.value: round(value, 4) for key, value in weights.items()},
        "budget_yen": budget,
        "household": household_value.value,
    }


def act_rank_areas(state: SessionState, limit: int = 5) -> dict[str, Any]:
    if state.criteria is None:
        return {
            "error": "criteria_not_set",
            "message": "먼저 set_criteria로 조건을 확정해야 합니다.",
            "areas": [],
        }

    capped = max(1, min(limit, MAX_RANKING_LIMIT))
    ranked = state.usecases.rank.execute(state.criteria, limit=capped)
    state.last_ranking = ranked

    return {
        "areas": [
            {
                "station_id": row.station.id,
                "name_ko": row.station.name_ko,
                "name_ja": row.station.name_ja,
                "ward": row.station.ward,
                "lat": row.station.lat,
                "lon": row.station.lon,
                "score": round(row.score.total, 1),
                "rent_yen": row.rent_yen,
                "commute_minutes": row.commute_minutes,
                "top_drivers": [
                    {"metric": key.value, "contribution": round(value, 2)}
                    for key, value in row.score.top_drivers(3)
                ],
            }
            for row in ranked
        ]
    }


def act_explain_area(state: SessionState, station_id: str) -> dict[str, Any]:
    if state.criteria is None:
        return {"error": "criteria_not_set", "message": "먼저 조건을 확정해야 합니다."}
    try:
        explanation = state.usecases.explain.execute(station_id, state.criteria)
    except KeyError:
        return {"error": "unknown_station", "station_id": station_id}

    def detail(item: Any) -> dict[str, Any]:
        return {
            "metric": item.key.value,
            "percentile": round(item.percentile, 1),
            "contribution": round(item.contribution, 2),
            "is_missing": item.is_missing,
            "is_ward_resolution": item.is_ward_resolution,
        }

    return {
        "station_id": explanation.station.id,
        "name_ko": explanation.station.name_ko,
        "ward": explanation.station.ward,
        "score": round(explanation.total, 1),
        "rent_yen": explanation.rent_yen,
        "strengths": [detail(item) for item in explanation.strengths],
        "weaknesses": [detail(item) for item in explanation.weaknesses],
        "missing_metrics": [key.value for key in explanation.missing],
    }


def act_compare_areas(state: SessionState, station_ids: Sequence[str]) -> dict[str, Any]:
    if state.criteria is None:
        return {"error": "criteria_not_set", "message": "먼저 조건을 확정해야 합니다."}
    if len(station_ids) < 2:
        return {"error": "need_two_stations", "station_ids": list(station_ids)}
    try:
        comparison = state.usecases.compare.execute(station_ids, state.criteria)
    except KeyError as exc:
        return {"error": "unknown_station", "detail": str(exc)}

    return {
        "stations": [
            {"station_id": s.id, "name_ko": s.name_ko, "ward": s.ward}
            for s in comparison.stations
        ],
        "totals": {sid: round(total, 1) for sid, total in comparison.totals.items()},
        "differences": [
            {
                "metric": diff.key.value,
                "percentiles": {sid: round(p, 1) for sid, p in diff.percentiles.items()},
                "spread": round(diff.spread, 1),
            }
            for diff in comparison.differences
        ],
    }
```

`backend/src/chika/interface/agent/tools.py`:

```python
"""Agents SDK 툴 어댑터. 로직은 actions.py 에만 있다."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from chika.interface.agent import actions
from chika.interface.agent.state import SessionState


@function_tool
def set_criteria(
    ctx: RunContextWrapper[SessionState],
    korean_life: float,
    daily_convenience: float,
    quality_of_life: float,
    family: float,
    cost_risk: float,
    commute_to: str | None = None,
    commute_max_minutes: int | None = None,
    budget_min_yen: int | None = None,
    budget_max_yen: int | None = None,
    household: str = "single",
) -> dict[str, Any]:
    """사용자 조건을 확정한다. 다이얼 5개는 0~5의 상대 강도다."""
    return actions.act_set_criteria(
        ctx.context,
        korean_life=korean_life,
        daily_convenience=daily_convenience,
        quality_of_life=quality_of_life,
        family=family,
        cost_risk=cost_risk,
        commute_to=commute_to,
        commute_max_minutes=commute_max_minutes,
        budget_min_yen=budget_min_yen,
        budget_max_yen=budget_max_yen,
        household=household,
    )


@function_tool
def rank_areas(ctx: RunContextWrapper[SessionState], limit: int = 5) -> dict[str, Any]:
    """확정된 조건으로 역세권을 점수화해 상위 N곳을 반환한다."""
    return actions.act_rank_areas(ctx.context, limit=limit)


@function_tool
def explain_area(ctx: RunContextWrapper[SessionState], station_id: str) -> dict[str, Any]:
    """한 역의 점수를 지표별 기여도로 분해한다."""
    return actions.act_explain_area(ctx.context, station_id)


@function_tool
def compare_areas(
    ctx: RunContextWrapper[SessionState], station_ids: list[str]
) -> dict[str, Any]:
    """두 곳 이상을 비교해 차이 나는 축만 반환한다."""
    return actions.act_compare_areas(ctx.context, station_ids)
```

`backend/src/chika/interface/agent/agents.py`:

```python
"""에이전트 2개 + in-process 핸드오프 (스펙 §5.2). A2A가 아니다."""

from __future__ import annotations

from agents import Agent

from chika.interface.agent.state import SessionState
from chika.interface.agent.tools import compare_areas, explain_area, rank_areas, set_criteria

_INTAKE_INSTRUCTIONS = """\
당신은 도쿄 거주 한국인의 "어디 살까"를 돕는 상담자입니다. 한국어로 답합니다.

역할은 조건 수집 하나뿐입니다. 순위를 직접 말하지 마세요.

수집할 것:
- 다이얼 5개의 상대 강도 (0~5): 한국 생활 / 생활 편의 / 삶의 질 / 가족 / 비용·리스크
- 통근지와 상한 시간, 월세 예산, 가구 형태(single/couple/family)

규칙:
1. 조건이 모호하면 되묻습니다. 추측해서 채우지 않습니다.
2. 조건이 충분해지면 set_criteria를 호출하고, 곧바로 AnalysisAgent에게 넘깁니다.
3. 도쿄 23区 밖(요코하마·사이타마·오사카 등)은 데이터가 없습니다.
   범위 밖 요청은 정중히 거절하고 23区 내에서 대안을 제안하세요.
"""

_ANALYSIS_INSTRUCTIONS = """\
당신은 역세권 분석 결과를 한국어로 설명하는 분석가입니다.

절대 규칙:
1. 숫자는 툴이 반환한 값만 씁니다. 어떤 수치도 직접 계산하거나 추정하지 마세요.
   툴 결과에 없는 숫자를 문장에 넣으면 안 됩니다.
2. 순위 이유는 top_drivers/strengths의 지표로 설명합니다. 이유를 지어내지 마세요.
3. 단점(weaknesses)을 숨기지 않습니다.
4. is_ward_resolution이 true인 지표는 "이 수치는 역세권이 아니라 구 단위입니다"를
   반드시 함께 적습니다.
5. missing_metrics에 있는 지표는 "데이터 없음"으로 표기합니다. 점수 50점처럼 말하지 마세요.
6. 투자 판단·수익률·매수 시점에 대한 조언은 하지 않습니다. 데이터를 제시하고
   판단은 사용자에게 돌려주세요.
7. "서울로 치면 어디"같은 감각 번역은 데이터가 아니라 서술임을 명시합니다.

흐름: rank_areas로 후보를 얻고, 사용자가 특정 역을 물으면 explain_area,
둘 이상을 비교하면 compare_areas를 씁니다.
"""


def build_agents(state: SessionState) -> Agent[SessionState]:
    """진입 에이전트(IntakeAgent)를 반환한다. state는 Runner.run(context=...)로 넘긴다."""
    analysis: Agent[SessionState] = Agent(
        name="AnalysisAgent",
        instructions=_ANALYSIS_INSTRUCTIONS,
        tools=[rank_areas, explain_area, compare_areas],
    )
    intake: Agent[SessionState] = Agent(
        name="IntakeAgent",
        instructions=_INTAKE_INSTRUCTIONS,
        tools=[set_criteria],
        handoffs=[analysis],
    )
    return intake
```

- [ ] **Step 4: 테스트 통과를 확인한다**

Run: `cd backend && uv run pytest -v && uv run mypy src`
Expected: 104 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/interface backend/tests/interface backend/pyproject.toml
git commit -m "feat: IntakeAgent/AnalysisAgent 골격과 툴 액션"
```

---

### Task 12: 아키텍처 가드 + Phase 0 종료 검증

**Files:**
- Create: `backend/tests/test_architecture.py`
- Create: `backend/src/chika/interface/cli.py`
- Test: `backend/tests/interface/test_cli_smoke.py`
- Modify: `backend/README.md`
- Modify: `README.md` (루트, Phase 0 완료 표기)

**Interfaces:**
- Consumes: 모든 이전 태스크
- Produces:
  - `build_demo_session() -> SessionState` — 시드 데이터로 구성된 세션
  - CLI: `uv run python -m chika.interface.cli` — LLM 없이 조건 → 랭킹 → 설명을 한 번 출력

**설계 메모:** 아키텍처 가드는 **테스트로 강제한다.** 규칙을 문서에만 적으면 3주 뒤에 깨진다. `domain` 이 외부 패키지를 import 하는 순간 빨간불이 켜져야 한다.

CLI는 Phase 0의 종료 증거다. OpenAI 키 없이도 "조건 → 랭킹 → 근거"가 끝까지 도는 것을 보여준다.

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`backend/tests/test_architecture.py`:

```python
"""계층 규칙을 테스트로 강제한다. 문서에만 적으면 3주 뒤에 깨진다."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "chika"

#: domain이 써도 되는 표준 라이브러리. 이 밖의 import는 위반이다.
_ALLOWED_STDLIB = {
    "abc", "collections", "dataclasses", "enum", "functools", "hashlib",
    "itertools", "math", "random", "statistics", "types", "typing", "__future__",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _modules(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def test_domain_layer_exists() -> None:
    assert _modules("domain"), "domain 모듈이 하나도 없다"


def test_domain_imports_nothing_but_stdlib_and_itself() -> None:
    violations: list[str] = []
    for path in _modules("domain"):
        for root in _imported_roots(path):
            if root == "chika" or root in _ALLOWED_STDLIB:
                continue
            violations.append(f"{path.relative_to(SRC)} imports {root}")
    assert not violations, f"domain 계층의 외부 의존: {violations}"


def test_domain_does_not_import_outer_layers() -> None:
    forbidden = ("chika.application", "chika.infrastructure", "chika.interface", "chika.etl")
    violations: list[str] = []
    for path in _modules("domain"):
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(SRC)} -> {name}" for name in forbidden if name in source
        )
    assert not violations, f"의존 방향 위반: {violations}"


def test_application_imports_only_domain() -> None:
    forbidden = ("chika.infrastructure", "chika.interface", "chika.etl")
    violations: list[str] = []
    for path in _modules("application"):
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path.relative_to(SRC)} -> {name}" for name in forbidden if name in source
        )
    assert not violations, f"의존 방향 위반: {violations}"


def test_openai_sdk_never_appears_in_domain_or_application() -> None:
    violations: list[str] = []
    for layer in ("domain", "application"):
        for path in _modules(layer):
            roots = _imported_roots(path)
            if "agents" in roots or "openai" in roots or "pydantic" in roots:
                violations.append(str(path.relative_to(SRC)))
    assert not violations, f"LLM/pydantic 의존이 안쪽 계층에 있다: {violations}"
```

`backend/tests/interface/test_cli_smoke.py`:

```python
from chika.interface.cli import build_demo_session, run_demo
from chika.interface.agent.actions import act_rank_areas, act_set_criteria


def test_demo_session_ranks_end_to_end() -> None:
    state = build_demo_session()
    act_set_criteria(
        state,
        korean_life=4.0, daily_convenience=2.0, quality_of_life=1.0,
        family=0.0, cost_risk=2.0, budget_max_yen=160_000,
    )
    result = act_rank_areas(state, limit=5)
    assert len(result["areas"]) == 5
    assert result["areas"][0]["score"] >= result["areas"][-1]["score"]


def test_run_demo_prints_a_ranking(capsys) -> None:  # type: ignore[no-untyped-def]
    run_demo()
    output = capsys.readouterr().out
    assert "1." in output
    assert "근거" in output
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd backend && uv run pytest tests/test_architecture.py tests/interface/test_cli_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.interface.cli'` (아키텍처 테스트는 이미 통과할 수 있다. 통과하면 그대로 두고 CLI만 구현한다.)

- [ ] **Step 3: 최소 구현**

`backend/src/chika/interface/cli.py`:

```python
"""Phase 0 종료 증거. OpenAI 키 없이 조건 → 랭킹 → 근거를 한 번 출력한다."""

from __future__ import annotations

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.rank_areas import RankAreas
from chika.infrastructure.fake.repositories import (
    FakeAreaMetricsRepository,
    FakeCommuteRepository,
    FakePriceRepository,
)
from chika.infrastructure.fake.seed import build_seed
from chika.interface.agent.actions import act_explain_area, act_rank_areas, act_set_criteria
from chika.interface.agent.state import SessionState, UseCases


def build_demo_session(count: int = 40) -> SessionState:
    stations, raws, commute, prices = build_seed(count=count)
    areas = FakeAreaMetricsRepository(stations, raws)
    return SessionState(
        usecases=UseCases(
            rank=RankAreas(areas, FakeCommuteRepository(commute), FakePriceRepository(prices)),
            explain=ExplainArea(areas, FakePriceRepository(prices)),
            compare=CompareAreas(areas),
        )
    )


def run_demo() -> None:
    state = build_demo_session()
    act_set_criteria(
        state,
        korean_life=4.0,
        daily_convenience=2.0,
        quality_of_life=1.0,
        family=0.0,
        cost_risk=2.0,
        budget_max_yen=160_000,
        household="single",
    )
    ranking = act_rank_areas(state, limit=5)

    print("=== Chika Lens Phase 0 (시드 데이터) ===")
    print("조건: 한국 생활 중시, 예산 16만엔 이하, 1인 가구\n")

    for index, area in enumerate(ranking["areas"], start=1):
        rent = f"{area['rent_yen']:,}엔" if area["rent_yen"] is not None else "데이터 없음"
        print(f"{index}. {area['name_ko']} ({area['ward']})  점수 {area['score']}  월세 {rent}")

    top_id = ranking["areas"][0]["station_id"]
    detail = act_explain_area(state, top_id)
    print(f"\n[1위 근거] {detail['name_ko']}")
    for item in detail["strengths"]:
        note = " (구 단위 지표)" if item["is_ward_resolution"] else ""
        print(f"  + {item['metric']}: 상위 {100 - item['percentile']:.0f}%{note}")
    for item in detail["weaknesses"]:
        print(f"  - {item['metric']}: 상위 {100 - item['percentile']:.0f}%")
    if detail["missing_metrics"]:
        print(f"  ! 데이터 없음: {', '.join(detail['missing_metrics'])}")


if __name__ == "__main__":
    run_demo()
```

- [ ] **Step 4: 전체 검증**

Run:

```bash
cd backend && uv run pytest -v && uv run ruff check . && uv run mypy src && uv run python -m chika.interface.cli
```

Expected: 전체 테스트 통과, ruff/mypy 통과, CLI가 5개 역 랭킹과 1위 근거를 출력

- [ ] **Step 5: 문서 갱신**

`backend/README.md` 끝에 추가:

```markdown
## Phase 0 데모

    uv run python -m chika.interface.cli

시드 데이터로 "조건 → 랭킹 → 근거"가 끝까지 도는 것을 확인한다. OpenAI 키가 필요 없다.

## 역 마스터 생성

    uv run python -m chika.etl.build_stations --n02 <N02.geojson> --n03 <N03.geojson>

국토수치정보 GeoJSON은 https://nlftp.mlit.go.jp/ksj/ 에서 수동으로 받는다.
```

루트 `README.md` 의 다음 단계 항목을 Phase 0 완료로 갱신하고 `docs/superpowers/plans/2026-09-03-chika-lens-phase0.md` 를 링크한다.

- [ ] **Step 6: 커밋**

```bash
git add backend README.md
git commit -m "feat: 아키텍처 가드 테스트와 Phase 0 데모 CLI"
```

---

## Phase 0 종료 기준

전부 만족해야 Phase 1로 넘어간다.

- [ ] `uv run pytest` 전부 통과 (약 110개)
- [ ] `uv run ruff check .` / `uv run mypy src` 통과
- [ ] `uv run python -m chika.interface.cli` 가 랭킹 5곳과 1위 근거를 출력
- [ ] `tests/test_architecture.py` 가 domain 계층의 외부 의존 0을 보증
- [ ] `data/stations.json` 에 도쿄 23구 역이 200~350개 들어 있음 (Task 10 Step 5)
- [ ] 결측 지표가 화면에 "데이터 없음"으로, 구 단위 지표가 "구 단위"로 표기됨

## Phase 0에서 하지 않는 것 (경계 확인)

- BigQuery / MLIT / Places API 실제 호출 — Phase 1·2
- `lookup_places` 툴 (스펙 §5.2) — Places API 실시간 호출이 필요하므로 Phase 2
- 가치 갭 회귀 — Phase 3 (Phase 1+2 데이터 필요)
- FastAPI / SSE / Next.js — Phase 4
- 실제 LLM 왕복 테스트 — 키와 비용이 필요하므로 Phase 4의 수동 확인으로 미룬다
- 통근 시간 실측 테이블 — Phase 1에서 역 간 소요시간 데이터를 넣기 전까지 Fake 유지

## 스펙 미결 사항과의 관계

스펙 §11의 세 항목은 Phase 0을 막지 않는다.

1. **평가 기간 이후 파생물 보유 가능 여부** — Phase 2 착수 전까지 약관을 확인한다. Phase 0은 외부 데이터를 쓰지 않으므로 영향 없음.
2. **신청 이메일** — 이미 `duswp220@gmail.com` 으로 제출됨. 거절 시 도메인 이메일로 재신청.
3. **GCP 프로젝트 확정** — Phase 2 착수 시점에 필요. Phase 0은 영향 없음.
