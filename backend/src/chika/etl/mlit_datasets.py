"""国土交通省 不動産情報ライブラリ 데이터셋 정의 — 지표와 엔드포인트의 유일한 대응처.

엔드포인트 번호(XKT006 등)는 문서만 보고는 무엇인지 알 수 없다. 실제 응답의
`_index` 필드에 데이터셋 이름이 들어 있어 그것으로 확인했다 (2026-09-08 실측).
`label` 은 그 실측값이고, 잘못된 엔드포인트를 가리키면 배치가 즉시 알아채도록
클라이언트가 대조한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: 타일 줌. z=13 이면 도쿄 489역을 59타일로 덮는다. 같은 영역을 z=14 로 넷으로
#: 쪼개 받아도 고유 건수가 같았으므로 (2026-09-08 실측) 타일당 잘림은 없다.
TILE_ZOOM = 13


@dataclass(frozen=True)
class MlitDataset:
    """타일 하나를 받는 GeoJSON 엔드포인트."""

    endpoint: str
    label: str
    #: 응답 `_index` 가 이 문자열로 시작해야 한다. 번호를 잘못 적으면 다른
    #: 데이터셋이 200으로 조용히 돌아오므로, 값이 아니라 정체를 검증한다.
    index_prefix: str


PRESCHOOL = MlitDataset("XKT007", "幼稚園・保育所", "bs006_preschool")
SCHOOL = MlitDataset("XKT006", "学校", "bs005_school")

#: 지표 11(육아·교육)의 구성. Google Aggregate 를 대체한다 — 인가 시설의 공식
#: 등록부라 학원·어학원이 섞이지 않는다 (스펙 §6.2.5).
CHILDCARE_DATASETS: Sequence[MlitDataset] = (PRESCHOOL, SCHOOL)

#: XKT006 중 육아·교육 지표에 넣을 학교 종별. 고교·대학·전수학교는 뺀다 —
#: 아이를 키우는 가구가 통학 거리를 따지는 것은 초등·중학이고, 대학은 오히려
#: 학생 거리(街)의 신호라 다른 지표와 뜻이 겹친다.
SCHOOL_KINDS_COUNTED: frozenset[str] = frozenset({"小学校", "中学校", "義務教育学校"})
