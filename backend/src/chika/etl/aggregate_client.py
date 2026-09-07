"""Places Aggregate API HTTP 클라이언트.

호출 1건 = computeInsights 1회 = 과금 1요청 (2026-09-07 실측).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from chika.etl.aggregate_queries import STATION_RADIUS_M, AggregateQuery

ENDPOINT = "https://areainsights.googleapis.com/v1:computeInsights"

#: 문서상 분당 1,200. 여유를 두고 초당 15건으로 제한한다.
_MIN_INTERVAL_SECONDS = 1.0 / 15

Transport = Callable[[str, bytes, dict[str, str]], bytes]


class AggregateApiError(RuntimeError):
    """API가 오류를 돌려줬다. 메시지에서 키는 마스킹된다."""


def _urllib_transport(url: str, body: bytes, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload: bytes = response.read()
        return payload


class AggregateClient:
    """카운트 조회 전용. 배치가 쓰고 런타임은 쓰지 않는다."""

    def __init__(
        self,
        api_key: str,
        transport: Transport = _urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep
        self._last_call_at = 0.0
        self.calls_made = 0

    def count(self, query: AggregateQuery, lat: float, lon: float) -> int:
        """반경 800m 안에서 조건에 맞는 장소 수. 호출 1건을 쓴다."""
        self._throttle()
        body: dict[str, object] = {
            "insights": ["INSIGHT_COUNT"],
            "filter": {
                "locationFilter": {
                    "circle": {
                        "latLng": {"latitude": lat, "longitude": lon},
                        "radius": STATION_RADIUS_M,
                    }
                },
                "typeFilter": {"includedTypes": list(query.included_types)},
                "operatingStatus": ["OPERATING_STATUS_OPERATIONAL"],
            },
        }
        if query.min_rating is not None:
            location_filter = body["filter"]
            assert isinstance(location_filter, dict)
            location_filter["ratingFilter"] = {"minRating": query.min_rating}

        try:
            raw = self._transport(
                ENDPOINT,
                json.dumps(body).encode("utf-8"),
                {"Content-Type": "application/json", "X-Goog-Api-Key": self._api_key},
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AggregateApiError(
                f"HTTP {exc.code}: {detail.replace(self._api_key, '<REDACTED>')}"
            ) from exc

        self.calls_made += 1
        payload = json.loads(raw.decode("utf-8"))
        # count는 정수가 아니라 문자열로 온다 ("42"). protobuf int64의 JSON 직렬화
        # 규칙이다. int() 를 빠뜨리면 퍼센타일이 문자열 비교로 조용히 망가진다.
        return int(str(payload.get("count", 0)))

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if self._last_call_at and elapsed < _MIN_INTERVAL_SECONDS:
            self._sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_call_at = time.monotonic()
