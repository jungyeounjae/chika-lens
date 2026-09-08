"""좌표 거리 계산. 외부 의존 0.

주변 역을 지도에 표시하는 데 쓴다. 역 좌표는 이미 로컬에 있으므로
API 호출이 필요 없다 — 이 계산이 그 값을 쓸모 있게 만든다.
"""

from __future__ import annotations

import math

#: 지구 평균 반지름. 도쿄 23구 규모에서 구면 근사로 충분하다.
EARTH_RADIUS_M = 6_371_000.0


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """하버사인 거리(미터)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
