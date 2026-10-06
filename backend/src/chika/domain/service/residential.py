"""주거 대상이 아닌 역 판별 (스펙 §8.3).

공항·크루즈터미널·관청가·물류단지는 생활 인프라 밀도로 구분되지 않는다 —
공항에도 편의점과 클리닉은 많다. 그래서 **용도지역이 주거가 아니라는 것**을
기본 조건으로 두고, 그 위에 "일상 장을 보는 사람이 없다"(슈퍼 0곳) 또는
"집 거래가 없다"(시세 결측) 중 하나를 요구한다.

하드 필터가 아니라 **플래그**다. 東大島·潮見처럼 용도지역 격자 때문에 비율이
낮게 나온 실제 주거지가 섞여 있어서, 판정이 틀려도 사용자가 되돌릴 수 있어야 한다.
"""

from __future__ import annotations

from chika.domain.model.metrics import MetricKey, RawMetrics

#: 주거전용지역 비율 문턱. 실측(489역)에서 2%·5%·10%가 16·17·17역으로 거의
#: 같아서, 이 값에 결과가 민감하지 않다.
RESIDENTIAL_RATIO_THRESHOLD = 0.05


def is_non_residential(raw: RawMetrics) -> bool:
    """주거 대상이 아닐 가능성이 높은 역이면 True.

    용도지역 비율이 결측이면 판단하지 않는다 — 데이터를 못 받은 것을
    비주거의 증거로 쓰지 않는다.
    """
    ratio = raw.get(MetricKey.RESIDENTIAL_ZONE_RATIO)
    if ratio is None or ratio >= RESIDENTIAL_RATIO_THRESHOLD:
        return False
    no_supermarket = raw.get(MetricKey.SUPERMARKET) == 0
    no_price = raw.get(MetricKey.PRICE_LEVEL) is None
    return no_supermarket or no_price
