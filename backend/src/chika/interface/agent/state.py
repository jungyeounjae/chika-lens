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
