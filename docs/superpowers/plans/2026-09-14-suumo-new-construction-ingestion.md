# SUUMO 신축 데이터 수집 레이어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 도쿄 23구 SUUMO 신축 분양 페이지를 주기적으로 크롤링해 물건명·주소·가격대·전용면적·인도시기를 수집하고, GSI 주소검색 API로 위경도를 붙여 `data/new_construction.json` 에 기록한다.

**Architecture:** 기존 `chika.etl.build_prices` (MLIT 배치)와 동일한 구조를 그대로 따른다 — HTTP 클라이언트는 transport 주입(테스트에서 실제 네트워크 없음), 파싱은 순수 함수, 영속화는 DB 없이 `data/*.json` 파일, 원본은 `data/.cache/` 에 캐시, 실행은 `uv run python -m chika.etl.build_new_construction` CLI. 도메인 계층(domain/model, domain/repository)은 건드리지 않는다 — `build_prices.py` 가 `Transaction` 을 domain이 아니라 `etl/mlit_prices.py` 안에 두는 것과 같은 이유로, `NewConstructionListing` 도 아직 application/interface 가 소비하지 않는 순수 ETL 산출물이라 `etl/` 안에 둔다. 이 구조를 application 이 실제로 소비하게 되는 시점(다음 계획 "공간 DB 결합")에서 필요하면 그때 포트를 추가한다 — 지금 추가하면 구현체 하나짜리 인터페이스가 된다.

**Tech Stack:** Python 3.12, 표준 라이브러리 `urllib`(HTTP, 기존 `mlit_client.py` 와 동일), `beautifulsoup4`(신규 의존성, HTML 파싱), pytest.

**Spec:** 이 대화에서 사용자가 제시한 "신축 공급 추적 에이전트" 구상의 1번(데이터 수집 레이어)만을 범위로 한다. 재개발 고시 파싱, 공간 DB 결합(재해·인프라 자동 평가), 시세 적정성 엔진, 에이전트 UI는 각각 별도 계획이다.

## Global Constraints

- Python `>=3.12,<3.13`, `from __future__ import annotations` 모든 파일 상단.
- `ruff` lint 통과 (`select = ["E", "F", "I", "UP", "B", "TID"]`), `mypy --strict` 통과.
- domain/application 계층에서 `pydantic` 금지 (ruff TID251) — 이 계획은 domain/application 을 건드리지 않으므로 해당 없음, 언급만.
- 신규 파일은 `backend/src/chika/etl/` 아래, 테스트는 `backend/tests/etl/` 아래 (기존 디렉토리 구조를 그대로 따른다).
- 크롤링은 robots.txt 확인 완료(2026-09-14, `https://suumo.jp/robots.txt` — `/ms/shinchiku/tokyo/sc_*/` 계열은 `Disallow` 목록에 없음, `/ms/shinchiku/brand_list/*/` 만 금지). 요청 간격 2초 이상, `User-Agent` 로 자기 신원을 밝힌다. 개인 이메일 등 사용자 개인정보는 어떤 헤더에도 넣지 않는다.
- HTML 마크업이 예상과 다르면 조용히 건너뛰지 않고 예외를 던진다(`mlit_prices.py::TransactionShapeError` 와 같은 철학) — 파싱 실패를 결측으로 접으면 사이트 개편을 몇 달 뒤에야 알아챈다.

---

## 사전 조사 결과 (실측, 2026-09-14)

이 계획의 모든 셀렉터·필드명은 브라우저로 실제 SUUMO 신축 페이지(`https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/`, `sc_setagaya/`)를 열어 DOM을 직접 읽어 확인한 것이다 — 가짜 셀렉터 없음.

**물건 카드 구조** (`div.cassette.property_unit` 하나가 물건 하나):
```html
<div class="cassette property_unit">
  <div class="cassette-content ...">
    <div class="cassette_header ...">
      <h2><a href="/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/" class="cassette_header-title">リビオ高田馬場</a></h2>
    </div>
    ...
    <div class="cassette-result_detail">
      <div class="cassette_basic">
        <ul class="cassette_basic-list">
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">所在地</p>
              <p class="cassette_basic-value">新宿区下落合１</p>
            </div>
          </li>
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">交通</p>
              <p class="cassette_basic-value">ＪＲ山手線/高田馬場 徒歩9分</p>
            </div>
          </li>
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">引渡時期</p>
              <p class="cassette_basic-value">2027年4月下旬予定</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="cassette_price cassette_price--layout">
        <ul class="cassette_price-list">
          <li class="cassette_price-list_item">
            <div class="cassette_price-value">
              <span class="cassette_price-accent">9890万円～1億7290万円</span>
              &nbsp;（先着順）
            </div>
            <p class="cassette_price-description">2LDK・3LDK
            / 55.08m<sup>2</sup>～76.56m<sup>2</sup></p>
          </li>
        </ul>
      </div>
    </div>
  </div>
</div>
```
가격 미정인 물건(예: ジオ飯田橋, `nc_67735307`)은 `cassette_price-accent` 안이 `価格未定` 텍스트다.

**페이지네이션** (세타가야구, 33건 → 2페이지):
```html
<div class="sortbox_pagination">
<ol class="sortbox_pagination-parts">
<li class="sortbox_pagination-list sortbox_pagination--current">1</li><li>&nbsp;</li><li class="sortbox_pagination-list"><a class="sortbox_pagination-link" href="/ms/shinchiku/tokyo/sc_setagaya/?page=2">2</a></li></ol>
</div>
```
`?page=N` 을 그대로 쿼리스트링으로 붙이면 해당 페이지가 온다 — "다음" 링크를 따라갈 필요 없이, 1페이지에서 최대 페이지 번호를 읽어 `range(2, max+1)` 로 바로 순회할 수 있다.

**23구 URL 슬러그** (`https://suumo.jp/ms/shinchiku/tokyo/` 에서 실측):
`港区=minato, 渋谷区=shibuya, 新宿区=shinjuku, 中央区=chuo, 千代田区=chiyoda, 中野区=nakano, 世田谷区=setagaya, 品川区=shinagawa, 文京区=bunkyo, 北区=kita, 台東区=taito, 墨田区=sumida, 江東区=koto, 荒川区=arakawa, 足立区=adachi, 葛飾区=katsushika, 江戸川区=edogawa, 目黒区=meguro, 大田区=ota, 杉並区=suginami, 練馬区=nerima, 豊島区=toshima, 板橋区=itabashi`

**지오코딩** — 국토지리원(GSI) 주소검색 API, 무료·키 불필요:
```
GET https://msearch.gsi.go.jp/address-search/AddressSearch?q=東京都新宿区下落合１
→ [{"geometry":{"coordinates":[139.699585,35.71574],"type":"Point"},"properties":{...}}]
```
(coordinates 는 `[lon, lat]` 순서다.) SUUMO 의 소재지 텍스트는 도도부현이 빠져 있으므로(`新宿区下落合１`) 검색 전에 `東京都` 를 붙인다 — 붙이지 않으면 동명 지명이 있는 다른 현으로 지오코딩될 수 있다.

---

## Task 1: 23구 URL 슬러그 매핑

**Files:**
- Create: `backend/src/chika/etl/suumo_wards.py`
- Test: `backend/tests/etl/test_suumo_wards.py`

**Interfaces:**
- Produces: `TOKYO_23_WARDS: dict[str, str]` — key는 구 이름(예: `"新宿区"`), value 는 URL 슬러그(예: `"shinjuku"`). Task 5(build 스크립트)가 이걸로 순회한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_suumo_wards.py
"""23구 슬러그 매핑 — 개수와 형태만 지킨다(값 자체는 실측 상수)."""

from __future__ import annotations

from chika.etl.suumo_wards import TOKYO_23_WARDS


def test_all_23_wards_are_present() -> None:
    assert len(TOKYO_23_WARDS) == 23


def test_every_ward_name_ends_with_ku() -> None:
    assert all(ward.endswith("区") for ward in TOKYO_23_WARDS)


def test_every_slug_is_lowercase_ascii() -> None:
    assert all(slug.isascii() and slug.islower() for slug in TOKYO_23_WARDS.values())


def test_shinjuku_maps_to_its_real_suumo_slug() -> None:
    """실측(2026-09-14, https://suumo.jp/ms/shinchiku/tokyo/) 값 하나를 고정으로."""
    assert TOKYO_23_WARDS["新宿区"] == "shinjuku"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_wards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.suumo_wards'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/suumo_wards.py
"""도쿄 23구 이름 <-> SUUMO 신축 페이지 URL 슬러그.

https://suumo.jp/ms/shinchiku/tokyo/ 의 구별 링크(`/ms/shinchiku/tokyo/sc_<slug>/`)를
실측해서 고정한 상수다(2026-09-14). SUUMO 가 슬러그를 바꾸는 일은 거의 없지만,
바뀌면 build_new_construction.py 가 그 구만 0건으로 보고하므로 알아챌 수 있다.
"""

from __future__ import annotations

TOKYO_23_WARDS: dict[str, str] = {
    "千代田区": "chiyoda",
    "中央区": "chuo",
    "港区": "minato",
    "新宿区": "shinjuku",
    "文京区": "bunkyo",
    "台東区": "taito",
    "墨田区": "sumida",
    "江東区": "koto",
    "品川区": "shinagawa",
    "目黒区": "meguro",
    "大田区": "ota",
    "世田谷区": "setagaya",
    "渋谷区": "shibuya",
    "中野区": "nakano",
    "杉並区": "suginami",
    "豊島区": "toshima",
    "北区": "kita",
    "荒川区": "arakawa",
    "板橋区": "itabashi",
    "練馬区": "nerima",
    "足立区": "adachi",
    "葛飾区": "katsushika",
    "江戸川区": "edogawa",
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_wards.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/suumo_wards.py backend/tests/etl/test_suumo_wards.py
git commit -m "feat(etl): 23구 SUUMO URL 슬러그 매핑 추가"
```

---

## Task 2: SUUMO HTTP 클라이언트

**Files:**
- Create: `backend/src/chika/etl/suumo_client.py`
- Test: `backend/tests/etl/test_suumo_client.py`

**Interfaces:**
- Consumes: 없음(최하위 계층).
- Produces: `SuumoClient` (transport 주입 가능, 기본은 실제 urllib), `SuumoClient.fetch_html(url: str) -> str`, `SuumoFetchError(RuntimeError)`. Task 5가 이 클라이언트로 페이지를 받아온다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_suumo_client.py
"""SuumoClient — 스로틀, 재시도. mlit_client.py 테스트와 같은 구조."""

from __future__ import annotations

import urllib.error

import pytest

from chika.etl.suumo_client import SuumoClient, SuumoFetchError


def test_fetch_html_returns_decoded_body() -> None:
    def transport(url: str) -> bytes:
        return "<html>ok</html>".encode("utf-8")

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    assert client.fetch_html("https://suumo.jp/x") == "<html>ok</html>"


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
        return b"<html>ok</html>"

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    assert client.fetch_html("https://suumo.jp/x") == "<html>ok</html>"
    assert len(attempts) == 3


def test_a_not_found_is_not_retried() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    client = SuumoClient(transport=transport, sleep=lambda _: None)
    with pytest.raises(SuumoFetchError, match="404"):
        client.fetch_html("https://suumo.jp/x")
    assert len(attempts) == 1


def test_calls_are_throttled_at_least_two_seconds_apart() -> None:
    sleeps: list[float] = []

    def transport(url: str) -> bytes:
        return b"<html>ok</html>"

    client = SuumoClient(transport=transport, sleep=lambda seconds: sleeps.append(seconds))
    client._last_call_at = __import__("time").monotonic()  # 직전 호출이 방금 있었던 것처럼
    client.fetch_html("https://suumo.jp/x")
    assert sleeps and sleeps[0] > 1.9
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.suumo_client'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/suumo_client.py
"""SUUMO 신축 분양 페이지 HTTP 클라이언트.

공개 사이트 스크래핑이다 — robots.txt 확인(2026-09-14, `/ms/shinchiku/tokyo/sc_*/`
계열은 불허 목록에 없음) 후 개인용으로 얌전히 돈다: 요청 간격 2초 이상,
User-Agent 로 자기 신원을 밝힌다(개인 이메일 등은 넣지 않는다).
mlit_client.py 와 같은 transport 주입 패턴이라 테스트가 실제 네트워크를 타지 않는다.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable

_MIN_INTERVAL_SECONDS = 2.0
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume batch)"

Transport = Callable[[str], bytes]


class SuumoFetchError(RuntimeError):
    """페이지를 받아오지 못했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body: bytes = response.read()
        return body


class SuumoClient:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def fetch_html(self, url: str) -> str:
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise SuumoFetchError(f"HTTP {exc.code}: {url}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise SuumoFetchError(f"연결 실패: {exc.reason}") from exc
            self.calls_made += 1
            return raw.decode("utf-8", errors="replace")
        raise SuumoFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다: {url}")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/suumo_client.py backend/tests/etl/test_suumo_client.py
git commit -m "feat(etl): SUUMO HTTP 클라이언트 추가 (스로틀+재시도)"
```

---

## Task 3: HTML 파싱 (beautifulsoup4 의존성 추가 포함)

**Files:**
- Modify: `backend/pyproject.toml` (etl optional-dependencies 에 `beautifulsoup4` 추가)
- Create: `backend/src/chika/etl/suumo_new_construction.py`
- Test: `backend/tests/etl/test_suumo_new_construction.py`

**Interfaces:**
- Consumes: 없음(순수 함수, HTML 문자열만 받는다).
- Produces: `NewConstructionListing`(frozen dataclass), `SuumoShapeError(RuntimeError)`, `parse_price_range(text: str) -> tuple[int | None, int | None]`, `parse_area_range(text: str) -> tuple[float | None, float | None]`, `max_page_number(html: str) -> int`, `parse_listing_page(html: str, ward: str, base_url: str = "https://suumo.jp") -> list[NewConstructionListing]`. Task 5가 이 함수들로 크롤링 결과를 파싱한다.

- [ ] **Step 1: pyproject.toml 수정**

`backend/pyproject.toml` 의 `etl` 항목을 다음으로 바꾼다 (기존 `shapely`/`pyproj` 옆에 추가):

```toml
etl = ["shapely>=2.0", "pyproj>=3.6", "beautifulsoup4>=4.12"]
```

표준 라이브러리 `html.parser` 백엔드로 쓴다(`BeautifulSoup(html, "html.parser")`) — `lxml` 은 더 빠르지만 이 정도 배치 규모(구당 최대 수십 건)에는 체감 차이가 없어 의존성을 하나 더 늘릴 이유가 없다.

Run: `cd backend && uv sync --extra etl`
Expected: `beautifulsoup4` 설치됨

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_suumo_new_construction.py
"""SUUMO 물건 카드 파싱 — 실측 HTML(2026-09-14, sc_shinjuku/) 을 축약한 픽스처."""

from __future__ import annotations

import pytest

from chika.etl.suumo_new_construction import (
    SuumoShapeError,
    max_page_number,
    parse_area_range,
    parse_listing_page,
    parse_price_range,
)

# 실측: https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/ 의 "リビオ高田馬場" 카드.
LISTING_WITH_PRICE = """
<div class="cassette property_unit">
  <div class="cassette-content">
    <div class="cassette_header">
      <h2><a href="/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/" class="cassette_header-title">リビオ高田馬場</a></h2>
    </div>
    <div class="cassette-result_detail">
      <div class="cassette_basic">
        <ul class="cassette_basic-list">
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">所在地</p>
              <p class="cassette_basic-value">新宿区下落合１</p>
            </div>
          </li>
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">引渡時期</p>
              <p class="cassette_basic-value">2027年4月下旬予定</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="cassette_price cassette_price--layout">
        <ul class="cassette_price-list">
          <li class="cassette_price-list_item">
            <div class="cassette_price-value">
              <span class="cassette_price-accent">9890万円～1億7290万円</span>
            </div>
            <p class="cassette_price-description">2LDK・3LDK / 55.08m<sup>2</sup>～76.56m<sup>2</sup></p>
          </li>
        </ul>
      </div>
    </div>
  </div>
</div>
"""

# 실측: 같은 페이지의 "ジオ飯田橋" 카드 — 가격 미정.
LISTING_PRICE_UNDECIDED = """
<div class="cassette property_unit">
  <div class="cassette-content">
    <div class="cassette_header">
      <h2><a href="/ms/shinchiku/tokyo/sc_shinjuku/nc_67735307/" class="cassette_header-title">ジオ飯田橋</a></h2>
    </div>
    <div class="cassette-result_detail">
      <div class="cassette_basic">
        <ul class="cassette_basic-list">
          <li class="cassette_basic-list_item">
            <div class="cassette_basic-item">
              <p class="cassette_basic-title">所在地</p>
              <p class="cassette_basic-value">新宿区新小川町</p>
            </div>
          </li>
        </ul>
      </div>
      <div class="cassette_price cassette_price--layout">
        <ul class="cassette_price-list">
          <li class="cassette_price-list_item">
            <div class="cassette_price-value">
              <span class="cassette_price-accent">価格未定</span>
            </div>
            <p class="cassette_price-description">1LDK～3LDK / 43.94m<sup>2</sup>～151.39m<sup>2</sup></p>
          </li>
        </ul>
      </div>
    </div>
  </div>
</div>
"""

# 실측: https://suumo.jp/ms/shinchiku/tokyo/sc_setagaya/ (33건 -> 2페이지).
PAGINATION_TWO_PAGES = """
<div class="sortbox_pagination">
<ol class="sortbox_pagination-parts">
<li class="sortbox_pagination-list sortbox_pagination--current">1</li><li>&nbsp;</li>
<li class="sortbox_pagination-list"><a class="sortbox_pagination-link" href="/ms/shinchiku/tokyo/sc_setagaya/?page=2">2</a></li>
</ol>
</div>
"""


def test_a_price_range_is_parsed_to_yen() -> None:
    assert parse_price_range("9890万円～1億7290万円") == (98_900_000, 172_900_000)


def test_an_undecided_price_is_missing_not_zero() -> None:
    assert parse_price_range("価格未定") == (None, None)


def test_a_single_price_without_a_range_is_both_min_and_max() -> None:
    assert parse_price_range("1億2490万円") == (124_900_000, 124_900_000)


def test_an_area_range_is_parsed_to_sqm() -> None:
    assert parse_area_range("2LDK・3LDK / 55.08m2～76.56m2") == (55.08, 76.56)


def test_max_page_number_reads_the_pagination_links() -> None:
    assert max_page_number(PAGINATION_TWO_PAGES) == 2


def test_a_single_page_ward_has_no_pagination_links() -> None:
    assert max_page_number("<div>물건 23건, 페이지네이션 없음</div>") == 1


def test_parsing_a_listing_with_a_price_range() -> None:
    listings = parse_listing_page(LISTING_WITH_PRICE, ward="新宿区")
    assert len(listings) == 1
    listing = listings[0]
    assert listing.suumo_id == "67733465"
    assert listing.name == "リビオ高田馬場"
    assert listing.ward == "新宿区"
    assert listing.address_raw == "新宿区下落合１"
    assert listing.price_min_yen == 98_900_000
    assert listing.price_max_yen == 172_900_000
    assert listing.floor_area_min_sqm == 55.08
    assert listing.floor_area_max_sqm == 76.56
    assert listing.delivery_period_raw == "2027年4月下旬予定"
    assert listing.url == "https://suumo.jp/ms/shinchiku/tokyo/sc_shinjuku/nc_67733465/"
    assert listing.lat is None and listing.lon is None  # 지오코딩 전 단계


def test_parsing_a_listing_with_an_undecided_price() -> None:
    listings = parse_listing_page(LISTING_PRICE_UNDECIDED, ward="新宿区")
    assert listings[0].price_min_yen is None
    assert listings[0].price_max_yen is None
    assert listings[0].floor_area_min_sqm == 43.94
    assert listings[0].floor_area_max_sqm == 151.39


def test_a_page_with_no_cards_returns_an_empty_list() -> None:
    """물건 0건인 구가 실제로 있을 수 있다 — 빈 리스트는 유효한 답이다."""
    assert parse_listing_page("<div>no cards here</div>", ward="千代田区") == []


def test_a_card_missing_its_title_link_raises_instead_of_silently_skipping() -> None:
    broken = '<div class="cassette property_unit"><p>제목 없음</p></div>'
    with pytest.raises(SuumoShapeError):
        parse_listing_page(broken, ward="新宿区")
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_new_construction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.suumo_new_construction'`

- [ ] **Step 4: 구현**

```python
# backend/src/chika/etl/suumo_new_construction.py
"""SUUMO 신축 분양 목록 페이지 파싱 — HTTP 도, 지오코딩도 하지 않는다.

셀렉터는 전부 실측이다(2026-09-14, `sc_shinjuku/`·`sc_setagaya/` 실제 DOM).
마크업이 바뀌면 조용히 0건으로 접지 않고 SuumoShapeError 를 던진다 —
mlit_prices.py::TransactionShapeError 와 같은 이유: 결측으로 접으면
사이트 개편을 몇 달 뒤에야 알아챈다.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class SuumoShapeError(RuntimeError):
    """SUUMO 마크업이 예상과 다르다."""


@dataclass(frozen=True)
class NewConstructionListing:
    """신축 물건 하나. lat/lon 은 아직 지오코딩 전이라 None 일 수 있다."""

    suumo_id: str
    name: str
    ward: str
    address_raw: str
    lat: float | None
    lon: float | None
    price_min_yen: int | None
    price_max_yen: int | None
    floor_area_min_sqm: float | None
    floor_area_max_sqm: float | None
    delivery_period_raw: str
    url: str
    fetched_at: str


_YEN_PATTERN = re.compile(r"(?:(\d+)億)?(?:(\d+)万)?円")
_AREA_PATTERN = re.compile(r"([\d.]+)m")
_PAGE_PATTERN = re.compile(r"\?page=(\d+)")
_ID_PATTERN = re.compile(r"nc_(\d+)")


def _parse_yen(text: str) -> int:
    match = _YEN_PATTERN.search(text)
    if not match or (match.group(1) is None and match.group(2) is None):
        raise SuumoShapeError(f"금액 포맷이 아니다: {text!r}")
    oku = int(match.group(1) or 0)
    man = int(match.group(2) or 0)
    return oku * 100_000_000 + man * 10_000


def parse_price_range(text: str) -> tuple[int | None, int | None]:
    """"9890万円～1億7290万円" -> (98900000, 172900000). "価格未定" -> (None, None)."""
    text = text.strip()
    if "円" not in text:
        return None, None
    parts = text.split("～")
    if len(parts) == 1:
        price = _parse_yen(parts[0])
        return price, price
    return _parse_yen(parts[0]), _parse_yen(parts[1])


def parse_area_range(text: str) -> tuple[float | None, float | None]:
    """"2LDK・3LDK / 55.08m2～76.56m2" -> (55.08, 76.56). 간형이 하나뿐이면 둘 다 같은 값."""
    area_part = text.rsplit("/", 1)[-1]
    numbers = _AREA_PATTERN.findall(area_part)
    if not numbers:
        return None, None
    if len(numbers) == 1:
        value = float(numbers[0])
        return value, value
    return float(numbers[0]), float(numbers[-1])


def max_page_number(html: str) -> int:
    """페이지네이션에 있는 가장 큰 page 번호. 페이지네이션이 없으면(=1페이지 뿐) 1."""
    numbers = [int(n) for n in _PAGE_PATTERN.findall(html)]
    return max(numbers, default=1)


def parse_listing_page(
    html: str, ward: str, base_url: str = "https://suumo.jp"
) -> list[NewConstructionListing]:
    """물건 목록 페이지 하나(=`?page=N` 한 장)를 파싱한다. 0건은 유효한 결과다 —
    호출부(build_new_construction.py)가 구 전체 합계를 보고 이상을 판단한다."""
    soup = BeautifulSoup(html, "html.parser")
    today = dt.date.today().isoformat()
    listings: list[NewConstructionListing] = []

    for cassette in soup.select(".property_unit"):
        title_tag = cassette.select_one(".cassette_header-title")
        href = title_tag.get("href") if title_tag else None
        if not title_tag or not href or not isinstance(href, str):
            raise SuumoShapeError(
                "물건 제목/링크(.cassette_header-title)를 찾지 못했다 — "
                "SUUMO 마크업이 바뀌었을 수 있다"
            )
        url = urljoin(base_url, href)
        id_match = _ID_PATTERN.search(url)
        if id_match is None:
            raise SuumoShapeError(f"URL 에서 물건 id(nc_숫자)를 못 찾았다: {url!r}")

        basics: dict[str, str] = {}
        for item in cassette.select(".cassette_basic-list_item"):
            label = item.select_one(".cassette_basic-title")
            value = item.select_one(".cassette_basic-value")
            if label is not None and value is not None:
                basics[label.get_text(strip=True)] = value.get_text(strip=True)

        price_tag = cassette.select_one(".cassette_price-accent")
        price_min, price_max = parse_price_range(price_tag.get_text(strip=True) if price_tag else "")

        description_tag = cassette.select_one(".cassette_price-description")
        area_min, area_max = parse_area_range(
            description_tag.get_text(strip=True) if description_tag else ""
        )

        listings.append(
            NewConstructionListing(
                suumo_id=id_match.group(1),
                name=title_tag.get_text(strip=True),
                ward=ward,
                address_raw=basics.get("所在地", ""),
                lat=None,
                lon=None,
                price_min_yen=price_min,
                price_max_yen=price_max,
                floor_area_min_sqm=area_min,
                floor_area_max_sqm=area_max,
                delivery_period_raw=basics.get("引渡時期", ""),
                url=url,
                fetched_at=today,
            )
        )
    return listings
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_suumo_new_construction.py -v`
Expected: PASS (11 passed)

- [ ] **Step 6: 커밋**

```bash
git add backend/pyproject.toml backend/src/chika/etl/suumo_new_construction.py backend/tests/etl/test_suumo_new_construction.py
git commit -m "feat(etl): SUUMO 신축 물건 카드 HTML 파싱 추가"
```

---

## Task 4: GSI 지오코더

**Files:**
- Create: `backend/src/chika/etl/gsi_geocoder.py`
- Test: `backend/tests/etl/test_gsi_geocoder.py`

**Interfaces:**
- Consumes: 없음.
- Produces: `GsiGeocoder`, `GsiGeocoder.geocode(address: str) -> tuple[float, float] | None`(lat, lon), `GeocodeFetchError(RuntimeError)`. Task 5가 주소 문자열을 넣어 위경도를 받는다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# backend/tests/etl/test_gsi_geocoder.py
"""GsiGeocoder — 국토지리원 주소검색 API 클라이언트."""

from __future__ import annotations

import json
import urllib.error

import pytest

from chika.etl.gsi_geocoder import GeocodeFetchError, GsiGeocoder


def _body(results: list[dict[str, object]]) -> bytes:
    return json.dumps(results).encode("utf-8")


def test_a_matched_address_returns_lat_lon() -> None:
    """실측(2026-09-14): 東京都新宿区下落合１ -> lon 139.699585, lat 35.71574."""

    def transport(url: str) -> bytes:
        return _body(
            [
                {
                    "geometry": {"coordinates": [139.699585, 35.71574], "type": "Point"},
                    "properties": {"title": "東京都新宿区下落合一丁目"},
                }
            ]
        )

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    lat, lon = geocoder.geocode("東京都新宿区下落合１")
    assert lat == pytest.approx(35.71574)
    assert lon == pytest.approx(139.699585)


def test_an_unmatched_address_is_missing_not_an_error() -> None:
    def transport(url: str) -> bytes:
        return _body([])

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    assert geocoder.geocode("존재하지 않는 주소") is None


def test_rate_limiting_is_retried_with_backoff() -> None:
    attempts: list[int] = []

    def transport(url: str) -> bytes:
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]
        return _body([{"geometry": {"coordinates": [139.7, 35.7]}, "properties": {}}])

    geocoder = GsiGeocoder(transport=transport, sleep=lambda _: None)
    assert geocoder.geocode("x") == (35.7, 139.7)
    assert len(attempts) == 2
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/etl/test_gsi_geocoder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chika.etl.gsi_geocoder'`

- [ ] **Step 3: 구현**

```python
# backend/src/chika/etl/gsi_geocoder.py
"""국토지리원(GSI) 주소검색 API — 무료, 키 불필요.

https://msearch.gsi.go.jp/address-search/AddressSearch?q=<주소>
실측(2026-09-14): "東京都新宿区下落合１" -> lon 139.699585, lat 35.71574
(coordinates 는 [lon, lat] 순서로 온다).

SUUMO 물건의 소재지는 도도부현이 빠져 있다("新宿区下落合１") — 호출부가
"東京都" 를 붙여서 넘겨야 한다. 여기서는 붙이지 않는다: 이 모듈은 도쿄
전용이 아니라 순수 지오코딩 어댑터이기 때문이다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

BASE_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

_MIN_INTERVAL_SECONDS = 0.5
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_USER_AGENT = "chika-lens-research/0.1 (personal, low-volume batch)"

Transport = Callable[[str], bytes]


class GeocodeFetchError(RuntimeError):
    """지오코딩 요청이 실패했다."""


def _urllib_transport(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        body: bytes = response.read()
        return body


class GsiGeocoder:
    def __init__(
        self,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0

    def geocode(self, address: str) -> tuple[float, float] | None:
        """(lat, lon). 매칭 실패 시 None(결측) — 주소 하나가 안 풀린다고 배치
        전체를 세울 이유가 없다(MLIT API 호출과 달리 이건 보조 지오코딩)."""
        query = urllib.parse.urlencode({"q": address})
        url = f"{BASE_URL}?{query}"
        self._throttle()
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                raw = self._transport(url)
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise GeocodeFetchError(f"HTTP {exc.code}: {address!r}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_ATTEMPTS:
                    self._sleep(2.0**attempt)
                    continue
                raise GeocodeFetchError(f"연결 실패: {exc.reason}") from exc

            results = json.loads(raw.decode("utf-8"))
            if not isinstance(results, list) or not results:
                return None
            geometry = results[0].get("geometry", {})
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                return None
            return float(coordinates[1]), float(coordinates[0])
        raise GeocodeFetchError(f"{_MAX_ATTEMPTS}회 재시도 후에도 실패했다: {address!r}")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/etl/test_gsi_geocoder.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/etl/gsi_geocoder.py backend/tests/etl/test_gsi_geocoder.py
git commit -m "feat(etl): GSI 주소검색 지오코더 추가"
```

---

## Task 5: 배치 스크립트 조립 (`build_new_construction.py`)

**Files:**
- Create: `backend/src/chika/etl/build_new_construction.py`

**Interfaces:**
- Consumes: `TOKYO_23_WARDS`(Task 1), `SuumoClient`/`SuumoFetchError`(Task 2), `NewConstructionListing`/`max_page_number`/`parse_listing_page`(Task 3), `GsiGeocoder`(Task 4).
- Produces: `data/new_construction.json` 파일. CLI 이므로 `build_prices.py` 와 같은 이유로 이 파일 자체에는 전용 테스트를 붙이지 않는다 — 기존 컨벤션 확인됨(`backend/tests/etl/` 에 `test_build_prices.py` 가 없다: 순수 로직만 아래 계층 모듈에서 테스트하고, CLI 조립은 Task 6의 수동 실행으로 검증한다).

- [ ] **Step 1: 구현**

```python
# backend/src/chika/etl/build_new_construction.py
"""신축 분양 마스터 배치 — SUUMO(도쿄 23구) 크롤링 + GSI 지오코딩.

MLIT API 는 공공데이터라 '현재 마케팅 중인 신축 분양가·모델하우스 일정'을
주지 않는다(실거래는 준공 후에나 잡힌다) — 그래서 이 배치만 외부 포털을
직접 크롤링한다. robots.txt 확인(2026-09-14): `/ms/shinchiku/tokyo/sc_*/`
계열은 불허 목록에 없다. 요청 간격 2초 이상으로 개인 용도 수준을 지킨다.

사용법:

    uv run python -m chika.etl.build_new_construction
    uv run python -m chika.etl.build_new_construction --wards shinjuku,shibuya
    uv run python -m chika.etl.build_new_construction --refresh
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chika.etl.gsi_geocoder import GeocodeFetchError, GsiGeocoder
from chika.etl.suumo_client import SuumoClient, SuumoFetchError
from chika.etl.suumo_new_construction import (
    NewConstructionListing,
    max_page_number,
    parse_listing_page,
)
from chika.etl.suumo_wards import TOKYO_23_WARDS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/new_construction.json"))
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("data/.cache/suumo_new_construction")
    )
    parser.add_argument(
        "--geocode-cache", type=Path, default=Path("data/.cache/geocode_cache.json")
    )
    parser.add_argument(
        "--wards", help="쉼표로 구분한 구 슬러그(예: shinjuku,shibuya). 생략하면 23구 전체."
    )
    parser.add_argument("--refresh", action="store_true", help="HTML 캐시를 무시하고 재수집")
    args = parser.parse_args()

    wards = _selected_wards(args.wards)
    client = SuumoClient()
    listings = _crawl_all_wards(client, wards, args.cache_dir, args.refresh)
    print(f"물건 {len(listings)}건 수집 (구 {len(wards)}개)")

    geocode_cache = _load_geocode_cache(args.geocode_cache)
    geocoder = GsiGeocoder()
    geocoded = _geocode_all(listings, geocoder, geocode_cache)
    args.geocode_cache.parent.mkdir(parents=True, exist_ok=True)
    args.geocode_cache.write_text(
        json.dumps(geocode_cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    missing = [item for item in geocoded if item.lat is None]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([_to_dict(item) for item in geocoded], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{args.out} 에 {len(geocoded)}건 기록 (지오코딩 결측 {len(missing)}건)")
    if missing:
        print("  결측:", ", ".join(f"{m.name}({m.address_raw})" for m in missing[:10]))


def _selected_wards(raw: str | None) -> dict[str, str]:
    if raw is None:
        return TOKYO_23_WARDS
    slugs = {s.strip() for s in raw.split(",") if s.strip()}
    by_slug = {slug: ward for ward, slug in TOKYO_23_WARDS.items()}
    unknown = slugs - set(by_slug)
    if unknown:
        sys.exit(f"모르는 구 슬러그: {sorted(unknown)}")
    return {by_slug[slug]: slug for slug in slugs}


def _crawl_all_wards(
    client: SuumoClient, wards: dict[str, str], cache_dir: Path, refresh: bool
) -> list[NewConstructionListing]:
    listings: list[NewConstructionListing] = []
    for ward, slug in wards.items():
        ward_listings = _crawl_ward(client, ward, slug, cache_dir, refresh)
        print(f"  {ward}: {len(ward_listings)}건")
        if not ward_listings:
            print(f"    경고: {ward} 물건이 0건이다 — 마크업이 바뀌었을 수 있다")
        listings.extend(ward_listings)
    return listings


def _crawl_ward(
    client: SuumoClient, ward: str, slug: str, cache_dir: Path, refresh: bool
) -> list[NewConstructionListing]:
    base_url = f"https://suumo.jp/ms/shinchiku/tokyo/sc_{slug}/"
    first_html = _fetch_cached(client, base_url, cache_dir / f"{slug}_1.html", refresh)
    pages = max_page_number(first_html)

    listings = list(parse_listing_page(first_html, ward))
    for page in range(2, pages + 1):
        page_url = f"{base_url}?page={page}"
        html = _fetch_cached(client, page_url, cache_dir / f"{slug}_{page}.html", refresh)
        listings.extend(parse_listing_page(html, ward))
    return listings


def _fetch_cached(client: SuumoClient, url: str, cache_path: Path, refresh: bool) -> str:
    if not refresh and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    try:
        html = client.fetch_html(url)
    except SuumoFetchError as exc:
        sys.exit(f"중단: {exc}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    return html


def _load_geocode_cache(path: Path) -> dict[str, list[float] | None]:
    if not path.exists():
        return {}
    loaded: dict[str, list[float] | None] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _geocode_all(
    listings: list[NewConstructionListing],
    geocoder: GsiGeocoder,
    cache: dict[str, list[float] | None],
) -> list[NewConstructionListing]:
    result: list[NewConstructionListing] = []
    for listing in listings:
        key = f"{listing.ward}{listing.address_raw}"
        if key not in cache:
            try:
                coords = geocoder.geocode(f"東京都{listing.ward}{listing.address_raw}")
            except GeocodeFetchError as exc:
                print(f"    지오코딩 실패, 결측으로 남긴다: {key} ({exc})")
                coords = None
            cache[key] = list(coords) if coords else None
        coords = cache[key]
        lat, lon = (coords[0], coords[1]) if coords else (None, None)
        result.append(
            NewConstructionListing(
                suumo_id=listing.suumo_id,
                name=listing.name,
                ward=listing.ward,
                address_raw=listing.address_raw,
                lat=lat,
                lon=lon,
                price_min_yen=listing.price_min_yen,
                price_max_yen=listing.price_max_yen,
                floor_area_min_sqm=listing.floor_area_min_sqm,
                floor_area_max_sqm=listing.floor_area_max_sqm,
                delivery_period_raw=listing.delivery_period_raw,
                url=listing.url,
                fetched_at=listing.fetched_at,
            )
        )
    return result


def _to_dict(listing: NewConstructionListing) -> dict[str, object]:
    return {
        "suumo_id": listing.suumo_id,
        "name": listing.name,
        "ward": listing.ward,
        "address_raw": listing.address_raw,
        "lat": listing.lat,
        "lon": listing.lon,
        "price_min_yen": listing.price_min_yen,
        "price_max_yen": listing.price_max_yen,
        "floor_area_min_sqm": listing.floor_area_min_sqm,
        "floor_area_max_sqm": listing.floor_area_max_sqm,
        "delivery_period_raw": listing.delivery_period_raw,
        "url": listing.url,
        "fetched_at": listing.fetched_at,
    }


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: mypy/ruff 통과 확인**

Run: `cd backend && uv run ruff check src/chika/etl/build_new_construction.py && uv run mypy src/chika/etl/build_new_construction.py`
Expected: 오류 없음

- [ ] **Step 3: 커밋**

```bash
git add backend/src/chika/etl/build_new_construction.py
git commit -m "feat(etl): 신축 분양 배치 스크립트 조립 (SUUMO 크롤+GSI 지오코딩)"
```

---

## Task 6: 실제 실행으로 수동 검증

배치 CLI 자체는 전용 단위 테스트가 없으므로(Task 5 참고), 실제 네트워크로 한 번 돌려서 산출물을 눈으로 확인한다 — 이게 이 계획의 "런타임 체크"다.

- [ ] **Step 1: 신주쿠구 한 곳만 갱신 실행**

```bash
cd backend && MLIT_API_KEY=dummy uv run python -m chika.etl.build_new_construction --wards shinjuku --refresh
```

Expected 출력 예: `신宿区: 23건`, `data/new_construction.json 에 23건 기록 (지오코딩 결측 0건)` 근처의 값. (`MLIT_API_KEY` 는 이 배치가 실제로 쓰지 않지만 다른 스크립트와 셸 세팅을 맞추기 위해 관례상 남긴다 — 없어도 동작한다면 빼도 된다.)

- [ ] **Step 2: 산출물 확인**

```bash
cat backend/data/new_construction.json | python3 -m json.tool | head -30
```

각 물건에 `name`, `address_raw`, `lat`/`lon`(숫자), `price_min_yen`/`price_max_yen`(정수 또는 둘 다 null), `delivery_period_raw` 가 채워졌는지 확인한다. `lat`/`lon` 이 `null` 인 항목이 있으면 그 `address_raw` 로 https://msearch.gsi.go.jp/address-search/AddressSearch?q=... 를 직접 호출해 실제로 매칭이 안 되는 주소인지 확인한다.

- [ ] **Step 3: 캐시 확인**

```bash
ls backend/data/.cache/suumo_new_construction/ backend/data/.cache/geocode_cache.json
```

`shinjuku_1.html` 이 있어야 한다(페이지네이션 없는 구라 `_1` 하나뿐). `geocode_cache.json` 에 주소별 좌표가 쌓였는지 확인한다.

- [ ] **Step 4: `.gitignore` 확인**

`data/.cache/` 가 이미 무시 대상인지 확인한다(다른 배치들의 캐시도 커밋되지 않아야 하는 것과 동일):

```bash
git check-ignore backend/data/.cache/suumo_new_construction/shinjuku_1.html
```

Expected: 경로가 출력됨(=무시 대상). 안 됐다면 `backend/.gitignore` 에 `data/.cache/` 를 추가한다.

- [ ] **Step 5: 전체 23구 실행(선택, 시간이 걸림)**

```bash
cd backend && uv run python -m chika.etl.build_new_construction
```

23구 × 평균 1~2페이지, 요청 간격 2초 → 대략 1~2분. 완료 후 `경고: ... 물건이 0건이다` 로그가 있는 구가 있으면 그 구의 캐시된 HTML(`data/.cache/suumo_new_construction/<slug>_1.html`)을 열어 실제로 물건이 없는지, 마크업이 바뀐 것인지 확인한다.

---

## Self-Review 체크리스트

- **스펙 커버리지**: 사용자가 제시한 "1. 데이터 수집 레이어" 중 "포털 크롤러"(SUUMO)는 Task 1~6이 구현한다. "재개발 고시 파싱"은 별도 데이터 소스(도쿄도 도시정비국)라 이 계획 범위 밖 — 사용자에게 다음 계획으로 안내 필요.
- **플레이스홀더 스캔**: 모든 코드 블록이 실행 가능한 완성 코드다. "TODO"/"적절히 처리" 류 없음.
- **타입 일관성**: `NewConstructionListing` 필드명이 Task 3(정의)·Task 5(`_to_dict`, `_geocode_all`)에서 동일. `SuumoClient.fetch_html`/`GsiGeocoder.geocode` 시그니처가 정의·소비 지점에서 일치.
- **도메인 계층 미변경**: `domain/model/`, `domain/repository.py` 에 아무것도 추가하지 않았음을 확인 — 다음 계획("공간 DB 결합")에서 application 이 이 데이터를 소비하게 될 때 포트를 추가한다.
