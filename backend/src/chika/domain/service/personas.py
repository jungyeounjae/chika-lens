"""가구 형태 → 다이얼 기본값.

실사용에서 "大久保는 신혼부부가 살기 좋은 동네야?" 에 "이 데이터만으로 단정할
수 없습니다" 가 나갔다. 원인은 세 개였고 그중 둘이 여기에 있다.

1. IntakeAgent 의 독해 표에 "아이"·"육아" 는 있어도 **가구 형태를 가리키는 말이
   없었다.** "신혼부부" 는 어느 행에도 맞지 않아 다이얼이 앞 턴 그대로 남았다 —
   조건이 바뀌지 않았으니 기여도도 그대로여서, 답변의 근거가 여전히 한식당과
   한국 식자재점이었다. 톤이 아니라 **조건이 반영되지 않은 것**이 본질이다.
2. `household` 는 받아도 월세 배수 한 곳에서만 쓰였고, 실데이터에서 월세
   리포지토리가 빈 Fake 라 **효과가 0** 이었다. couple 로 설정해도 점수는
   1원어치도 움직이지 않았다.

그래서 가구 형태에 다이얼 기본값을 붙인다. 페르소나를 **말에서 읽어내는 일**은
LLM 이 하고(무한한 표현: 신혼부부·자취생·유학생·노부부…), 그것이 **어느 축을
뜻하는지**는 여기서 정한다. 프롬프트에 숫자를 적으면 매번 다른 값이 나오고
테스트할 수도 없다.

값의 근거는 지표 구성이다 (`dials.DIAL_TO_METRICS`):

- COUPLE 의 `FAMILY` 를 0 이 아니라 2 로 둔다. 보육·교육은 아이가 있어야만
  쓸모 있는 것이 아니라 **몇 년 뒤를 보는 축**이고, 신혼부부가 집을 고를 때
  실제로 보는 것이다. 5 로 두면 아이 있는 가구와 구분이 없어진다.
- SINGLE 의 `FAMILY` 는 0 이다. 다이얼 0 은 "그 축을 보지 않는다" 이며,
  15지표 중 2개가 가중치에서 빠진다.
- `KOREAN_LIFE` 는 어느 가구 형태에도 넣지 않는다. 한국 생활 중시는 가구
  형태와 무관하고, 사용자가 말했을 때만 켜져야 한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from chika.domain.model.criteria import Household
from chika.domain.model.weights import Dial

#: 가구 형태가 함축하는 다이얼 강도. 0~5 스케일은 사용자 다이얼과 같다.
HOUSEHOLD_DIALS: Mapping[Household, Mapping[Dial, float]] = MappingProxyType(
    {
        Household.SINGLE: MappingProxyType(
            {
                Dial.DAILY_CONVENIENCE: 3.0,
                Dial.QUALITY_OF_LIFE: 3.0,
                Dial.FAMILY: 0.0,
                Dial.COST_RISK: 3.0,
            }
        ),
        Household.COUPLE: MappingProxyType(
            {
                Dial.DAILY_CONVENIENCE: 3.0,
                Dial.QUALITY_OF_LIFE: 3.0,
                Dial.FAMILY: 2.0,
                Dial.COST_RISK: 3.0,
            }
        ),
        Household.FAMILY: MappingProxyType(
            {
                Dial.DAILY_CONVENIENCE: 4.0,
                Dial.QUALITY_OF_LIFE: 3.0,
                Dial.FAMILY: 5.0,
                Dial.COST_RISK: 3.0,
            }
        ),
    }
)


def seed_dials(
    household: Household, spoken: Mapping[Dial, float]
) -> dict[Dial, float]:
    """가구 형태의 기본값으로 **사용자가 말하지 않은 축만** 채운다.

    `spoken` 은 이미 강도가 붙은 다이얼이다 — 앞 턴에서 읽어낸 것을 포함한다.
    거기에 있는 축은 건드리지 않는다. "아이 학교가 중요해요" 로 `FAMILY` 5 가
    켜진 뒤 "저희는 부부예요" 가 오면 5 를 2 로 **내려서는 안 된다**. 사용자가
    직접 말한 것이 가구 형태의 통계적 기본값보다 강하다.

    반대로 침묵한 축은 기본값이 낫다. 조건 없는 0 은 "안 본다" 는 뜻이고,
    가구 형태를 말한 사용자가 뜻한 것은 그게 아니다.
    """
    seeded = dict(spoken)
    for dial, strength in HOUSEHOLD_DIALS[household].items():
        if seeded.get(dial, 0.0) == 0.0:
            seeded[dial] = strength
    return seeded
