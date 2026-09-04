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
