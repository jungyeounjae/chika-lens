# 백엔드 자동 3D 트리거 규칙 — 설계

## 배경

"자동 출력" 이니셔티브의 두 번째 서브프로젝트. 첫 번째 서브프로젝트
([2026-09-15-frontend-multi-layer-overlay-design.md](2026-09-15-frontend-multi-layer-overlay-design.md))에서
프런트엔드가 `Overlay[]`로 여러 3D 결과를 동시에 표시할 수 있게 됐다. 이번은
그 다음 단계 — 백엔드 에이전트가 "신주쿠교엔은 살기 좋아?" 같은 일반적인
질문에도 관련 3D 시각화(재해위험·용도지역·공원·학교)를 스스로 판단해
호출하도록 `backend/src/chika/interface/agent/prompts.py`의 규칙을 확장한다.

세 번째 서브프로젝트(랜드마크 이름→좌표 해석)는 이 문서의 범위 밖이다.

## 현재 상태 조사 결과

- `park_polygons`/`school_facilities`는 이미 "공원 있어?", "아이 키우기
  좋아?" 같은 주제 질문만으로 호출된다 — "3D"라는 말이 필요 없다. 애초에
  이 둘은 "제안"이 아니라 이미 사실상 자동이다.
- `hazard_polygons`/`zoning_massing`은 사용자가 명시적으로 "3D/입체"라고
  말해야만 호출된다. 그렇지 않고 재해위험이나 residential_zone_ratio를
  물으면 `metric_distribution`/`explain_area`가 텍스트·백분위로만 답하고,
  답변 끝에 "원하시면 3D로도 보여드릴 수 있어요"라는 한 줄 제안만 붙는다
  (`prompts.py` 396-401행).
- **진짜 공백**: "신주쿠교엔은 살기 좋아?"처럼 역/장소 이름만 대고 일반적으로
  묻는 질문은 `lookup_station` → `explain_area`로 가는데, `explain_area`는
  순수 텍스트·다이얼 기여도 분해만 낸다 — 4개 3D 툴 중 어느 것도 이 흐름에서
  자동으로 호출되지 않는다. 이 공백을 메우는 것이 이번 스펙의 목적이다.

## 설계

### 적용 범위

- `explain_area` (역/장소 하나를 지목한 일반 조회) — 매번 적용.
- `rank_areas`의 **1위 결과만** — 여러 역이 나오는 랭킹에서 전부에 3D를
  붙이면 지도가 과밀해지므로, 가장 추천되는 1곳만 조건부 3D를 붙인다.
- `metric_distribution`은 범위 밖 — 이 툴은 "비교/분포"가 목적이라 성격이
  다르다. 기존 제안 한 줄(있다면)은 그대로 둔다.

### 트리거 표

`explain_area`의 `strengths`/`weaknesses` 배열(각 항목 `{"metric": "...", ...}`)
또는 `rank_areas` 1위 결과의 `top_drivers` 배열(같은 `{"metric": "...", ...}`
구조)에 아래 메트릭 키가 하나라도 있으면 해당 3D 툴을 그 자리에서 자동
호출한다:

| 3D 툴 | 트리거 조건 |
|---|---|
| `hazard_polygons(station_id)` | `"disaster_risk"`가 `strengths`/`weaknesses`(또는 `top_drivers`)에 있음 |
| `school_facilities(lat, lon)` | `"childcare_education"`, `"elementary_school"`, `"middle_school"` 중 하나라도 있음 |
| `park_polygons(lat, lon)` | `"park"`가 있음 |
| `zoning_massing(station_id)` | **조건 없음 — 매번 포함.** `residential_zone_ratio`는 다이얼 가중치가
항상 0이라 구조적으로 `strengths`/`weaknesses`/`top_drivers`에 절대 나타나지
않는다(기존 규칙, `prompts.py` 370행 부근). 그래서 "극단적일 때만"이라는
동일한 기준을 적용할 수 없다 — 대신 용도지역/동네 성격은 극단치 여부와
무관하게 "살기 좋아?"라는 질문 자체에 항상 유용한 기본 맥락으로 보고 매번
포함한다.

`child_friendly_venue`는 의도적으로 제외한다 — 육아 관련 다이얼에 속하지만
`school_facilities` 툴이 실제로 다루는 데이터(학교·보육시설)와 다른 카테고리
(가족 동반 시설)라, 이 항목으로 트리거하면 툴이 보여주는 데이터와 트리거
근거가 어긋난다.

`lat`/`lon`(park_polygons/school_facilities용)과 `station_id`
(hazard_polygons/zoning_massing용)는 이미 `explain_area`/`rank_areas` 응답에
있는 값을 그대로 쓴다 — 기존 park_polygons/school_facilities 규칙과 동일한
패턴(추가 조회 불필요).

### 동시 호출 상한

없음. 조건을 만족하는 툴은 전부 그 턴에 같이 부른다(최대 4개: zoning 1개 +
조건부 3개). 각 툴은 서로 다른 외부 API(MLIT/Overpass)라 병렬 호출이
가능하고, 이미 hazard_polygons가 이어서 metric_distribution을 부르는
기존 2-호출 패턴이 있다 — 이번 확장도 같은 성격의 지연시간 트레이드오프다.

### 기존 제안 문구와의 관계

`prompts.py` 396-401행의 "원하시면 3D로도 보여드릴 수 있어요" 제안은
유지하되, **자동 트리거 조건을 만족하지 못했을 때만** 붙인다(예:
`disaster_risk`가 top/bottom 3위 안에 안 들어 애매한 경우). 조건을 만족해
이미 자동으로 hazard_polygons/zoning_massing 등을 불렀다면 같은 턴에 또
제안하지 않는다 — 이미 보여준 것을 다시 보여주겠다고 제안하는 건 의미가
없다.

### 재트리거 억제

같은 대화(세션) 안에서 같은 역에 대해 이미 자동 호출한 3D 툴은, 그 역을
다시 물어도(예: "가격은?", "조금 더 자세히") 재호출하지 않는다 — 기존
hazard/zoning 제안 문구의 "이미 보여줬으면 또 제안 안 함" 규칙과 같은
성격이다. 이는 별도 상태 필드 없이, 기존 방식과 동일하게 **에이전트의
대화 맥락 기억에 의존한다** — 이 세션에서 이미 그 역에 대해 그 툴을
불렀다는 사실은 지금까지의 turn 히스토리에 이미 있다.

### 에러 처리

새로 추가하는 에러 처리는 없다 — 각 3D 툴은 이미 자신만의 실패 처리 규칙이
있다(예: `error: "mlit_unavailable"`이면 "지금 서버 문제로 못 가져왔다"고
사실대로 답한다). 어떤 메트릭이 `missing_metrics`에 있어 `strengths`/
`weaknesses`에 애초에 없다면, 그 메트릭 기준 트리거도 당연히 발동하지
않는다 — 결측을 트리거 조건 충족으로 오인하지 않는다(이 프로젝트의
"결측 vs 확정값" 원칙과 일치).

## 다루지 않는 것 (범위 밖)

- `metric_distribution`/`rank_areas`의 2위 이하 결과에 대한 자동 3D.
- 랜드마크 이름(역이 아닌 장소명)의 좌표 해석 — 다음 서브프로젝트.
- 동시 호출 상한을 두는 정교한 우선순위 로직 — "상한 없음"으로 결정됐다.

## 테스트

프롬프트 전용 변경이라 코드 단위 테스트가 없다 — 실제 채팅으로 검증한다:

- 재해위험이 상/하위 3위 안에 드는 역을 `explain_area`로 물어 `hazard_polygons`가
  자동으로 함께 호출되는지 확인.
- 학교/보육 관련 지표가 상/하위 3위 안에 드는 역을 물어 `school_facilities`가
  자동 호출되는지 확인.
- 공원이 상/하위 3위 안에 드는 역을 물어 `park_polygons`가 자동 호출되는지
  확인.
- 위 조건에 아무것도 안 걸리는 "평범한" 역을 물어 `zoning_massing`만
  자동으로 붙고 나머지 3개는 안 붙는지 확인.
- 조건을 만족 못 하는 경우(예: disaster_risk가 애매) 기존 제안 한 줄이 그대로
  나오는지 확인.
- `rank_areas`로 순위를 받은 뒤 1위 역에 대해서만 조건부 3D가 붙고 2위 이하는
  안 붙는지 확인.
- 같은 세션에서 같은 역을 다시 물었을 때 이미 보여준 3D 툴이 재호출되지
  않는지 확인.
