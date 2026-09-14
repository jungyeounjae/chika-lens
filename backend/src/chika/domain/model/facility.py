"""3D 시각화용 시설 값 객체 — etl 배치 산출물이 아니라 요청 단위 실시간 조회 결과.

etl.mlit_childcare.Facility 와 필드가 겹치지만 별개 타입이다 — domain 은 etl 을
몰라야 한다(Clean Architecture, README "계층 규칙"). infrastructure 어댑터
(MlitSchoolFacilitySource, Task 2)가 변환한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchoolFacility:
    facility_id: str
    name: str
    #: 유치원/보육시설 종별 또는 "小学校"/"中学校"/"義務教育学校" 원문 그대로
    #: (mlit_childcare.py 의 kind 를 그대로 옮긴다 — 지어내지 않는다).
    kind: str
    lat: float
    lon: float
    #: 조회 좌표로부터의 거리(m). NewConstructionQuietness.distance_m 과 같은
    #: 선례로 값 객체 안에 포함시킨다 — 정렬·표시에 바로 쓸 수 있게.
    distance_m: float
