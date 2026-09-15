"""대화 세션 상태. Agents SDK의 context로 전달된다 (스펙 §5.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from chika.application.usecase.compare_areas import CompareAreas
from chika.application.usecase.explain_area import ExplainArea
from chika.application.usecase.hazard_polygons import HazardPolygons
from chika.application.usecase.metric_distribution import MetricDistribution
from chika.application.usecase.metric_extremes import MetricExtremes
from chika.application.usecase.new_construction_search import NewConstructionSearch
from chika.application.usecase.park_polygons import ParkPolygons
from chika.application.usecase.rank_areas import RankAreas, RankedArea
from chika.application.usecase.school_facilities import SchoolFacilities
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
    #: 학교/보육시설 3D 시각화용 — 배치가 아니라 요청 단위 실시간 MLIT 호출이다
    #: (school_facilities.py 참고). 좌표 기반이라 역이든 신축 물건이든 쓴다.
    school_facilities: SchoolFacilities
    #: 공원 3D 시각화용 — 배치가 아니라 요청 단위 실시간 Overpass(OSM) 호출이다
    #: (park_polygons.py 참고). 좌표 기반이라 역이든 신축 물건이든 쓴다.
    park_polygons: ParkPolygons
    #: SUUMO 신축 분양 물건 검색 — 배치 산출물(new_construction_enriched.json)만
    #: 읽는다. 실시간 크롤링 없음.
    new_construction: NewConstructionSearch


def _no_op_ward_crawl(_ward: str) -> None:
    """`ensure_ward_crawled`의 기본값 — 아무것도 안 한다.

    `SessionState`를 직접 만드는 테스트가 실수로 실제 SUUMO/MLIT 네트워크를
    타지 않게 하는 안전장치다. 실제 크롤링 훅은 `cli.py`(합성 루트)가
    `build_real_session`/`build_demo_session`에서 명시적으로 주입한다.
    """
    return None


@dataclass
class SessionState:
    usecases: UseCases
    criteria: SearchCriteria | None = None
    last_ranking: list[RankedArea] = field(default_factory=list)
    #: 직전 search_new_construction 결과 — explain_new_construction이 여기서
    #: 먼저 찾는다(rank_areas/explain_area가 last_ranking을 쓰는 것과 같은 패턴).
    last_new_construction: list[NewConstructionListing] = field(default_factory=list)
    #: 구 단위 lazy 크롤링 훅(`etl/lazy_new_construction.py::ensure_ward_crawled`
    #: 를 mlit_api_key 로 부분 적용한 것). 기본은 no-op.
    ensure_ward_crawled: Callable[[str], None] = _no_op_ward_crawl
    #: LLM 대화 이력. 없으면 매 턴이 백지에서 시작해
    #: "공원은 몇개야?" 가 무엇에 대한 질문인지 알 수 없다 (스펙 §5.5).
    history: Any | None = None
    #: hazard_polygons/zoning_massing/park_polygons 의 원본 GeoJSON 좌표
    #: 전체본 — 지도 렌더링(SSE)에는 필요하지만 모델이 텍스트로 답하는
    #: 데는 필요 없다. 툴은 좌표를 뺀 압축본만 반환해 LLM 대화 이력에
    #: 쌓이지 않게 하고(턴이 길어질수록 TPM 한도를 압박한 실측 문제),
    #: 전체본은 여기 툴 이름별 FIFO 큐로 쌓아 뒀다가 runner.py 가 SSE
    #: tool 이벤트를 만들 때 꺼내 쓴다.
    pending_overlay_payloads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
