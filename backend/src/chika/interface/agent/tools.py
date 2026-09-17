"""Agents SDK 툴 어댑터. 로직은 actions.py 에만 있다."""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from chika.interface.agent import actions
from chika.interface.agent.state import SessionState


@function_tool
def set_criteria(
    ctx: RunContextWrapper[SessionState],
    korean_life: float | None = None,
    daily_convenience: float | None = None,
    quality_of_life: float | None = None,
    family: float | None = None,
    cost_risk: float | None = None,
    commute_to: str | None = None,
    commute_max_minutes: int | None = None,
    budget_min_yen: int | None = None,
    budget_max_yen: int | None = None,
    household: str | None = None,
    exclude_wards: list[str] | None = None,
    focus_metric: str | None = None,
) -> dict[str, Any]:
    """사용자 조건을 확정한다. 다이얼 5개는 0~5의 상대 강도다.

    commute_to는 반드시 실제 역 이름(한국어/일본어) 또는 id여야 한다.
    unknown_commute_station 오류가 오면 후보를 사용자에게 되물어야 한다.

    **사용자가 지표 하나만 콕 집어 물었으면(예: "공원이 제일 많은 역은?",
    "카페 밀집도 높은 곳은?") `focus_metric`에 그 MetricKey 내부 키
    (예: `park`, `cafe`)를 넣습니다.** 다이얼(예: quality_of_life)로는
    안 됩니다 — 다이얼은 카페·공원·피트니스·음식점다양성을 한꺼번에
    묶어서, "공원만"이라는 뜻이 사라집니다. `focus_metric`을 채우면
    이 지표 하나에만 집중해서 순위가 계산됩니다. 예산·가구 형태 등
    다른 조건과 같이 물었으면 채우지 마세요 — 다이얼 기반 종합 랭킹이
    맞습니다. 이 필드는 매번 다시 판단합니다 — 생략하면 이전 값이
    유지되지 않고 꺼집니다(다른 필드와 다릅니다).
    """
    return actions.act_set_criteria(
        ctx.context,
        korean_life=korean_life,
        daily_convenience=daily_convenience,
        quality_of_life=quality_of_life,
        family=family,
        cost_risk=cost_risk,
        commute_to=commute_to,
        commute_max_minutes=commute_max_minutes,
        budget_min_yen=budget_min_yen,
        budget_max_yen=budget_max_yen,
        household=household,
        exclude_wards=exclude_wards or (),
        focus_metric=focus_metric,
    )


@function_tool
def lookup_station(ctx: RunContextWrapper[SessionState], name: str) -> dict[str, Any]:
    """역 이름으로 station_id 를 찾는다. explain_area·compare_areas 에 넘길 id 를 얻는다."""
    return actions.act_lookup_station(ctx.context, name)


@function_tool
def lookup_landmark(ctx: RunContextWrapper[SessionState], name: str) -> dict[str, Any]:
    """역이 아닌 지명(공원·랜드마크·관광지 등)으로 좌표와 가장 가까운 역을
    찾는다. lookup_station이 못 찾았을 때 이어서 쓴다. 결과의
    nearest_station.station_id를 explain_area 등에 그대로 넘긴다.
    far_from_any_station이 true면 그 사실을 답변에 반드시 밝힌다.
    """
    return actions.act_lookup_landmark(ctx.context, name)


@function_tool
def rank_areas(ctx: RunContextWrapper[SessionState], limit: int = 5) -> dict[str, Any]:
    """확정된 조건으로 역세권을 점수화해 상위 N곳을 반환한다.

    지표 하나만 콕 집은 질문이면 set_criteria 의 focus_metric 을 채운 뒤
    이 툴을 부르거나, 아예 metric_extremes(direction="best")를 씁니다.
    focus_metric 이 채워져 있으면 이 툴도 그 지표 하나만으로 정렬하므로
    (다이얼 전개를 건너뜀) 결과는 metric_extremes 와 같습니다 — 다만
    metric_extremes 는 세션에 남은 예산·통근 조건을 무시하고 항상 489역
    전체를 보는 반면, 이 툴은 그 필터가 그대로 적용됩니다.
    """
    return actions.act_rank_areas(ctx.context, limit=limit)


@function_tool
def explain_area(ctx: RunContextWrapper[SessionState], station_id: str) -> dict[str, Any]:
    """한 역의 점수를 지표별 기여도로 분해한다.

    `strengths`/`weaknesses`는 전체 지표 중 기여도 상위·하위 3개일 뿐,
    다른 다이얼에 밀려 활성 다이얼의 지표가 하나도 안 뜰 수 있다 —
    `by_dial`에 활성 다이얼(강도>0)마다 그 다이얼의 지표 전부가 있으니,
    "육아는?"처럼 다이얼 하나를 콕 집은 질문엔 새로 조회하지 말고 여기서
    가져다 쓴다.
    """
    return actions.act_explain_area(ctx.context, station_id)


@function_tool
def compare_areas(
    ctx: RunContextWrapper[SessionState], station_ids: list[str]
) -> dict[str, Any]:
    """두 곳 이상을 비교해 차이 나는 축만 반환한다."""
    return actions.act_compare_areas(ctx.context, station_ids)


@function_tool
def metric_distribution(
    ctx: RunContextWrapper[SessionState], station_id: str, metric: str
) -> dict[str, Any]:
    """한 역 주변의 지표 하나를 지도에 색칠할 재료로 낸다 (역 단위 percentile).

    사용자가 "지도로 보여줘", "주변은 어때" 처럼 한 지표의 공간적 분포를
    물을 때 쓴다. metric 은 내부 키(예: disaster_risk)다 — 모르면
    explain_area 로 먼저 확인한다.
    """
    return actions.act_metric_distribution(ctx.context, station_id, metric)


@function_tool
def ward_price_ranking(
    ctx: RunContextWrapper[SessionState],
    direction: str = "lowest",
    limit: int = 1,
    ward: str | None = None,
) -> dict[str, Any]:
    """구 단위 시세를 낸다 — 최저/최고 순위이거나, 특정 구 하나.

    "땅값/시세가 가장 낮은/높은 구는 어디야?" 에는 direction("lowest"
    또는 "highest")으로 답한다. **"○○区 시세는 어때?"처럼 특정 구를
    물으면 ward 인자에 그 구 이름(반드시 일본어, 예: "港区")을 넣는다** —
    direction/limit 만으로는 최저·최고 5위 밖의 중간권 구를 조회할 수
    없다. rank_areas 는 종합점수 순위라 이 질문에 쓸 수 없다.
    """
    return actions.act_ward_price_ranking(
        ctx.context, direction=direction, limit=limit, ward=ward
    )


@function_tool
def metric_extremes(
    ctx: RunContextWrapper[SessionState],
    metric: str,
    direction: str = "worst",
    limit: int = 5,
) -> dict[str, Any]:
    """489역 전체를 지표 하나로 정렬해 최악/최선 N곳을 낸다.

    "홍수가 잦은 곳은?", "치안이 나쁜 곳은?" 처럼 비교 기준 없이 지표
    하나만으로 극값을 물을 때 쓴다. direction 은 "worst" 또는 "best"다.
    결과는 이미 정렬돼 있다 — raw_value 를 보고 다시 순서를 뒤집지 않는다.
    """
    return actions.act_metric_extremes(ctx.context, metric=metric, direction=direction, limit=limit)


@function_tool
def hazard_polygons(
    ctx: RunContextWrapper[SessionState], station_id: str, radius_m: float = 800.0
) -> dict[str, Any]:
    """역 하나 주변의 홍수·토사재해·액상화·해일·쓰나미 **원본** MLIT Polygon (3D 시각화용).

    "이 역 침수 위험을 3D로/입체로 보여줘"처럼 원본 구역 경계·침수深 구간을
    묻는 질문에 쓴다. metric_distribution(정규화 percentile)과는 다른 툴이다.
    요청마다 MLIT을 실시간 호출하므로(과금 없음) 역 하나에만 쓴다.

    또한 사용자가 3D를 요청하지 않아도, explain_area/rank_areas 1위 결과의
    strengths/weaknesses/top_drivers 중 하나라도 metric이 "disaster_risk"이면
    그 응답을 받은 직후 자동으로(먼저 묻지 않고) 이 툴을 이어서 호출한다.
    """
    return actions.act_hazard_polygons(ctx.context, station_id, radius_m=radius_m)


@function_tool
def zoning_massing(
    ctx: RunContextWrapper[SessionState], station_id: str, radius_m: float = 500.0
) -> dict[str, Any]:
    """역 하나 주변의 용도지역 **원본** MLIT Polygon (3D 도시 밀도 시각화용).

    "이 역 주변 건물 밀도/저층·상업지역을 3D로 보여줘"처럼 물을 때 쓴다.

    또한 사용자가 3D를 요청하지 않아도, explain_area 또는 rank_areas 1위
    결과를 받으면 조건 없이 **매번** 그 직후 자동으로 이 툴을 이어서
    호출한다 — residential_zone_ratio는 다이얼 가중치가 0이라 strengths/
    weaknesses/top_drivers에 절대 나타나지 않으므로, 이 툴만 예외로
    무조건 자동 호출한다.
    """
    return actions.act_zoning_massing(ctx.context, station_id, radius_m=radius_m)


@function_tool
def search_new_construction(
    ctx: RunContextWrapper[SessionState],
    ward: str | None = None,
    address_contains: str | None = None,
    max_price_yen: int | None = None,
    min_price_yen: int | None = None,
    max_hazard_severity: float | None = None,
    min_daily_ridership: float | None = None,
    max_daily_ridership: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """SUUMO에서 수집한 도쿄 23구 **신축 분양** 물건을 검색한다.

    `rank_areas`(역세권 랭킹, 489역 기존 데이터)와는 완전히 다른 데이터다 —
    "신축", "분양", "모델하우스" 관련 질문에 이 툴을 쓴다. `set_criteria`로
    조건을 확정할 필요 없이 바로 호출 가능하다.

    `ward`는 반드시 일본어 구 이름(예: "新宿区", "미나토구"가 아니다).
    `address_contains`는 구보다 좁은 동네 이름 질문에 쓴다(예: "光が丘") —
    "히카리가오카에 뭐 있어?" 같은 질문은 ward만으론 표현이 안 된다. 주소
    (공식 町丁目)와 최근접 역명 둘 중 하나라도 포함하면 매치한다 — "히카리
    가오카" 같은 동네 이름은 공식 주소엔 안 나오고 역명으로만 나타나는
    경우가 많다. 가격순 정렬·상한 10건과 무관하게 이 조건만으로 걸러지므로
    가격 미정이거나 비싼 물건도 빠지지 않는다.
    `max_hazard_severity`(0~1, 낮을수록 안전)를 주면 그 값을 넘는 재해
    레이어가 하나라도 있는 물건을 제외한다 — "안전한 곳만"이면 0.5 정도를
    시작값으로 쓴다. `min_daily_ridership`/`max_daily_ridership`는 최근접
    역의 일평균 승하차인원(정숙도 프록시, 많을수록 번화가)으로 거른다 —
    "조용한 동네"면 max_daily_ridership를, "번화가"면 min_daily_ridership를
    쓴다. 가격은 전부 엔 단위(1억엔 = 100000000)다.

    결과는 세션에 저장되어, 이후 `explain_new_construction`으로 물건 하나를
    더 자세히 볼 수 있다. `hazard_summary`에 레이어가 없으면 "그 레이어
    데이터 없음"이지 "안전"이 아니다 — 답할 때 구분해서 말한다.
    """
    return actions.act_search_new_construction(
        ctx.context,
        ward=ward,
        address_contains=address_contains,
        max_price_yen=max_price_yen,
        min_price_yen=min_price_yen,
        max_hazard_severity=max_hazard_severity,
        min_daily_ridership=min_daily_ridership,
        max_daily_ridership=max_daily_ridership,
        limit=limit,
    )


@function_tool
def lookup_new_construction(ctx: RunContextWrapper[SessionState], name: str) -> dict[str, Any]:
    """신축 물건 이름으로 suumo_id 를 찾는다.

    사용자가 특정 물건 이름을 대며 물어볼 때(예: "프레시스 히카리가오카
    어때?") 쓴다. `search_new_construction`은 가격순 정렬 + 상한 10건이라
    가격 미정·고가 물건은 이름을 대도 결과에서 밀려날 수 있다 — 이 툴은
    그 정렬·상한과 무관하게 이름 부분일치로 찾는다. 한글 음차는 일본어로
    바꿔서 넘긴다. 결과의 `suumo_id`로 `explain_new_construction`을 불러
    자세히 본다.
    """
    return actions.act_lookup_new_construction(ctx.context, name)


@function_tool
def explain_new_construction(
    ctx: RunContextWrapper[SessionState], suumo_id: str
) -> dict[str, Any]:
    """신축 물건 하나의 전체 정보(가격·면적·인도시기·재해 요약·정숙도)를 낸다.

    `suumo_id`는 `search_new_construction`/`lookup_new_construction` 결과에
    있는 값을 그대로 쓴다.
    """
    return actions.act_explain_new_construction(ctx.context, suumo_id)


@function_tool
def school_facilities(
    ctx: RunContextWrapper[SessionState], lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 주변의 학교·유치원·보육시설 위치를 낸다 — 3D 지도 마커 재료.

    "아이 키우기 좋아?", "학교 가까워?", "이 동네 살기 좋아?"(교육 인프라
    맥락) 같은 질문에 쓴다. `lat`/`lon`은 `rank_areas`/`search_new_construction`
    결과에 이미 있는 좌표를 그대로 넘긴다 — 역이든 신축 물건이든 상관없다.

    결과가 0건이면 "이 반경 안에 학교/보육시설이 없다"는 뜻이지 조회 실패가
    아니다. `kind`는 원문 그대로(예: "小学校", "義務教育学校", 보육시설 종별) —
    한국어로 지어내 번역하지 않는다(자연스럽게 풀어서 설명하는 것은 괜찮다).

    또한 사용자가 묻지 않아도, explain_area/rank_areas 1위 결과의
    strengths/weaknesses/top_drivers 중 하나라도 metric이
    "childcare_education"/"elementary_school"/"middle_school"이면 그 응답을
    받은 직후 자동으로 이 툴을 이어서 호출한다.
    """
    return actions.act_school_facilities(ctx.context, lat=lat, lon=lon, radius_m=radius_m)


@function_tool
def park_polygons(
    ctx: RunContextWrapper[SessionState], lat: float, lon: float, radius_m: float = 800.0
) -> dict[str, Any]:
    """좌표 주변의 공원 원본 구역 경계(Polygon)를 낸다 — 3D 녹지 시각화 재료.

    "공원 있어?", "녹지 가까워?" 같은 질문에 쓴다. `lat`/`lon`은
    `rank_areas`/`search_new_construction`/`school_facilities` 결과에 이미
    있는 좌표를 그대로 넘긴다. 결과 0건은 "이 반경 안에 공원 없음"이지
    오류가 아니다. `name`이 `null`이면 OSM에 이름이 등록 안 된 공원이다 —
    "이름 미상의 공원"이라고 답하되 이름을 지어내지 않는다.

    또한 사용자가 묻지 않아도, explain_area/rank_areas 1위 결과의
    strengths/weaknesses/top_drivers 중 하나라도 metric이 "park"이면 그
    응답을 받은 직후 자동으로 이 툴을 이어서 호출한다.
    """
    return actions.act_park_polygons(ctx.context, lat=lat, lon=lon, radius_m=radius_m)
