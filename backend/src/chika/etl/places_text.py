"""지표 2 — 한국 식자재·미용 시설 (Places API New, Text Search).

Aggregate API에는 '한국 식자재점' 전용 타입이 없고 `grocery_store`에 섞인다
(스펙 §3.1). 텍스트 검색으로 보완한다.

**1회성 배치다.** 식자재점 분포는 달마다 바뀌지 않으므로 매월 돌릴 이유가 없다.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

#: 필드 마스크가 과금 티어를 정한다. id + primaryType 이면 Pro SKU이고
#: 월 5,000콜이 무료다 (489역 × 2쿼리 = 978콜). 이름·좌표를 받으면 더 비싸진다.
#: `places.id` 만 요청하면 Text Search Essentials (IDs Only) — 무료 무제한이다.
#: `primaryType` 을 하나 넣는 순간 Pro(월 5,000)로 올라간다.
#: 타입 필터는 응답이 아니라 **요청 파라미터**(`includedType`)로 건다.
FIELD_MASK = "places.id"

#: 韓国食材는 韓国食品과 거의 같은 결과를 낸다 — 실측 확인. 콜만 낭비된다.
#:
#: 韓国コスメ도 뺐다. 실측 결과 상업지구에서 일반 화장품점·드럭스토어·쇼핑몰을
#: 무차별로 잡아왔다 (銀座에서 ルミネ有楽町, 上野에서 ロクシタン). 텍스트 검색이
#: 느슨하게 매칭해 "한국"과 무관한 소매 밀도를 재게 된다.
KOREAN_QUERIES: Sequence[str] = ("韓国食品",)

#: 요청 시점에 서버가 거르게 한다.
#:
#: 응답에서 `primaryType` 을 보고 거르면 두 가지 손해가 있다 — 필드 마스크가
#: Pro 티어로 올라가고, 서버가 20건으로 자른 **뒤에** 거르므로 매칭을 잃는다.
#: 실측에서 신오쿠보가 10건에서 16건으로 늘었다 (스펙 §6.2.3).
#:
#: 검색어가 이미 "한국"을 강제하므로 이 타입 필터는 식자재점이 아닌 것을
#: 걸러내는 역할이다.
COUNTED_TYPE = "asian_grocery_store"

_MIN_INTERVAL_SECONDS = 1.0 / 10
Transport = Callable[[str, bytes, dict[str, str]], bytes]


def bounding_rectangle(lat: float, lon: float, radius_m: float) -> dict[str, object]:
    """반경을 감싸는 사각형.

    Text Search 의 `locationRestriction` 은 원을 받지 않는다. 외접 사각형은
    모서리만큼(약 27%) 넓지만, 모든 역에 같은 왜곡이 걸리므로 퍼센타일 순위에는
    영향이 없다.
    """
    dlat = radius_m / 111_320.0
    # 도쿄 위도에서 경도 1도는 위도 1도보다 짧다. 보정하지 않으면 동서로 좁아진다.
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return {
        "rectangle": {
            "low": {"latitude": lat - dlat, "longitude": lon - dlon},
            "high": {"latitude": lat + dlat, "longitude": lon + dlon},
        }
    }


def _urllib_transport(url: str, body: bytes, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload: bytes = response.read()
        return payload


class TextSearchClient:
    def __init__(
        self,
        api_key: str,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        radius_m: float = 800.0,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep
        self._radius = radius_m
        self._last_call_at = 0.0
        self.calls_made = 0

    def search(self, query: str, lat: float, lon: float) -> list[str]:
        """place id 목록. 한 페이지 상한은 20건이다.

        타입 필터를 요청에 실어 서버가 자르기 전에 거르게 한다.
        """
        self._throttle()
        body = {
            "textQuery": query,
            "includedType": COUNTED_TYPE,
            "locationRestriction": bounding_rectangle(lat, lon, self._radius),
            "languageCode": "ja",
        }
        try:
            raw = self._transport(
                ENDPOINT,
                json.dumps(body).encode("utf-8"),
                {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                },
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"HTTP {exc.code}: {detail.replace(self._api_key, '<REDACTED>')}"
            ) from exc

        self.calls_made += 1
        places = json.loads(raw.decode("utf-8")).get("places", [])
        return [str(p.get("id", "")) for p in places]

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()


def count_korean_shops(client: TextSearchClient, lat: float, lon: float) -> int:
    """역 반경 안의 한국 식자재점·화장품점 수.

    검색어끼리 같은 가게를 잡을 수 있으므로 place id로 중복을 제거한다.
    """
    found: set[str] = set()
    for query in KOREAN_QUERIES:
        found.update(place_id for place_id in client.search(query, lat, lon) if place_id)
    return len(found)
