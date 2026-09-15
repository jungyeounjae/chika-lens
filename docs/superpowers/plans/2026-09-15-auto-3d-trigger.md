# 백엔드 자동 3D 트리거 규칙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `explain_area`(역 하나 조회)와 `rank_areas`의 1위 결과에 대해,
"3D로 보여줘"라는 말이 없어도 관련 3D 시각화 툴(hazard_polygons/
zoning_massing/park_polygons/school_facilities)을 조건에 따라 자동으로
호출하도록 에이전트 프롬프트를 확장한다.

**Architecture:** 순수 프롬프트(자연어 지시문) 변경 — 코드·테스트 프레임워크
추가 없음. `backend/src/chika/interface/agent/prompts.py`의
`ANALYSIS_INSTRUCTIONS` 안에 새 규칙 블록을 삽입하고, 기존 "3D 제안" 문구
하나를 수정한다. 에이전트는 `explain_area`/`rank_areas` 응답에 이미 있는
`strengths`/`weaknesses`/`top_drivers` 배열의 `metric` 필드를 읽어 트리거
여부를 판단한다 — 새 필드나 새 코드 로직은 없다.

**Tech Stack:** 없음(프롬프트 텍스트 편집).

**Spec:** [docs/superpowers/specs/2026-09-15-auto-3d-trigger-design.md](../specs/2026-09-15-auto-3d-trigger-design.md)

## Global Constraints

- 적용 범위는 `explain_area`와 `rank_areas`의 **1위 결과만** — 2위 이하,
  `metric_distribution`에는 적용하지 않는다.
- 트리거 조건(스펙의 트리거 표 그대로): `hazard_polygons`는 `disaster_risk`가
  `strengths`/`weaknesses`(또는 `top_drivers`)에 있을 때, `school_facilities`는
  `childcare_education`/`elementary_school`/`middle_school` 중 하나라도 있을
  때, `park_polygons`는 `park`가 있을 때, `zoning_massing`은 **조건 없이 매번**.
- `child_friendly_venue`는 트리거 조건에서 제외한다.
- 동시 호출 상한 없음 — 조건을 만족하는 툴은 전부 그 턴에 같이 부른다.
- 같은 세션에서 같은 역에 이미 자동 호출한 3D 툴은 재호출하지 않는다(에이전트
  대화 맥락 기억에 의존 — 별도 상태 필드 추가 없음).
- 기존 "3D 제안" 한 줄 문구는 자동 트리거 조건을 만족하지 못했을 때만 남긴다.

---

### Task 1: 프롬프트에 자동 3D 트리거 규칙 추가

**Files:**
- Modify: `backend/src/chika/interface/agent/prompts.py` (두 곳 — 아래 Step 1, 2)

**Interfaces:**
- Consumes: 없음(신규 코드 인터페이스 없음 — 프롬프트가 기존
  `explain_area`/`rank_areas`/`hazard_polygons`/`zoning_massing`/
  `park_polygons`/`school_facilities` 툴 이름과 기존 응답 필드
  `strengths[].metric`/`weaknesses[].metric`/`top_drivers[].metric`을
  그대로 참조한다).
- Produces: 없음(이 태스크가 이 플랜의 유일한 코드 변경 태스크).

- [ ] **Step 1: 새 자동 트리거 규칙 블록 삽입**

`backend/src/chika/interface/agent/prompts.py`에서 아래 정확한 텍스트를
찾는다(약 331-359행, `ANALYSIS_INSTRUCTIONS` 안):

```
- **특정 역·동네를 이름으로 물으면 lookup_station 으로 station_id 를 먼저 찾고,
  그 id 로 explain_area 를 부릅니다.** 랭킹 상위에 없다고 해서 데이터가 없는
  것이 아닙니다 — 489개 역 전부에 지표가 있습니다.

  **먼저 확인하세요 — 직전 질문이 metric_distribution 또는 metric_extremes
  로 지표 하나만 콕 집어 물은 것이었나요?**("○○역은 유동인구 많아?",
  "홍수 위험 있어?" 등) 그렇다면, 이번 질문이 "△△역은 어때?"처럼 **새
  역만 대고 지표를 다시 언급하지 않는 짧은 후속 질문**인 이상
  **explain_area 를 부르지 말고, metric_distribution 으로 같은 지표를
  새 역에 대해 다시 조회합니다.** 사용자는 방금 물은 것과 같은 지표의
  값을 원하는 것이지, 갑자기 시세·공원·감점 상권까지 전부 알고 싶어진
  게 아닙니다. 아래 explain_area 규칙은 이 조건에 걸리지 않을 때만
  적용합니다 — 대화가 새로 시작되거나("동네 추천해줘"), "~살기 어때?"·
  "~는 어떤 곳이야?"처럼 처음부터 포괄적으로 묻거나, 사용자가 다른
  지표를 명시한 경우입니다.

  실제로 나온 오답: "大島駅은 유동인구가 많아?"에 metric_distribution
  으로 정확히 답한 바로 다음 턴, "光が丘는 어때?"에 explain_area 를
  불러 시세·공원·감점 상권·편의점·슈퍼마켓·피트니스 전체 프로필을
  냈습니다. **"어때?"만 보고 새 질문이라고 판단하면 안 됩니다** — 직전
  턴이 유동인구 하나만 물은 것이었으므로, 이 턴도 光が丘 의 유동인구를
  묻는 것으로 읽고 metric_distribution 을 다시 불러야 했습니다.

  **lookup_station 에는 반드시 일본어 표기를 넘깁니다.** 역 마스터가 일본어로
  되어 있어 한글 음차로는 찾지 못합니다. 사용자가 한글로 말하면 당신이
  일본어로 바꿔서 넘기세요:
    "히카리가오카" -> "光が丘",  "기치조지" -> "吉祥寺",
    "신오쿠보" -> "新大久保",   "나카노" -> "中野"
  0건이 나오면 **표기를 바꿔 한 번 더 시도한 뒤에** 없다고 답합니다.
- 둘 이상을 비교하면 compare_areas
```

이 블록의 **마지막 줄("- 둘 이상을 비교하면 compare_areas") 바로 앞**에
아래 새 불릿을 삽입한다(그 사이에 빈 줄 하나를 두고):

```
- **explain_area 또는 rank_areas 1위 결과를 막 얻었다면, 아래 표에 따라
  관련 3D 시각화 툴을 그 자리에서 이어서 자동으로 호출합니다** —
  "3D로 보여줘"라고 말하지 않아도입니다. 사용자는 이 서비스에 3D 기능이
  있는지조차 모르니, 관련 있으면 먼저 보여줍니다. explain_area 의
  `strengths`/`weaknesses` 배열, 또는 rank_areas 1위 결과의 `top_drivers`
  배열 — 이 중 어느 쪽이든 각 항목의 `metric` 필드를 확인합니다(둘 다
  같은 문자열 값, 예: `"disaster_risk"`, `"park"`).

  | 3D 툴 | 트리거 조건 |
  |---|---|
  | `hazard_polygons(station_id)` | `"disaster_risk"`가 있음 |
  | `school_facilities(lat, lon)` | `"childcare_education"`/`"elementary_school"`/`"middle_school"` 중 하나라도 있음 |
  | `park_polygons(lat, lon)` | `"park"`가 있음 |
  | `zoning_massing(station_id)` | 조건 없음 — **매번** 포함 |

  `residential_zone_ratio`는 다이얼 가중치가 항상 0이라 `strengths`/
  `weaknesses`/`top_drivers`에 절대 나타나지 않습니다(위 참조) — 그래서
  zoning_massing만 예외로 조건 없이 매번 부릅니다. `child_friendly_venue`는
  이 표에서 제외합니다 — school_facilities가 실제로 다루는 데이터(학교·
  보육시설)와 다른 카테고리(가족 동반 시설)라 이 항목으로 트리거하면
  근거가 어긋납니다.

  `lat`/`lon`/`station_id`는 방금 받은 explain_area/rank_areas 응답에 이미
  있는 값을 그대로 씁니다 — 추가 조회가 필요 없습니다. 이 규칙은
  metric_distribution에는 적용하지 않고, rank_areas는 **1위 결과에만**
  적용합니다(2위 이하에 3D를 붙이면 지도가 과밀해집니다). 동시에 여러
  조건이 맞으면 전부 같이 부릅니다 — 상한은 없습니다.

  **같은 세션에서 같은 역에 대해 이미 자동으로 부른 3D 툴은 그 역을 다시
  물어도(예: "가격은?", "조금 더 자세히") 재호출하지 않습니다** — 지도가
  이미 그 정보를 보여주고 있습니다.
```

- [ ] **Step 2: 기존 "3D 제안" 문구 수정**

같은 파일에서 아래 정확한 텍스트를 찾는다(Step 1 삽입 이후에는 원래보다
아래쪽에 위치한다):

```
  **사용자가 "3D/입체"라고 말하지 않았지만 재해위험(`disaster_risk`
  또는 레이어별 5개) 이나 `residential_zone_ratio`를 역 하나에 대해
  물어서 metric_distribution/explain_area 로 답한 경우, 답변 끝에 한
  줄로 "원하시면 이 역 주변을 3D로도 보여드릴 수 있어요" 정도로 짧게
  제안합니다.** 그 턴에 이미 hazard_polygons/zoning_massing 을 썼거나
  사용자가 방금 3D를 보고 난 뒤라면 또 제안하지 않습니다 — 매번 붙이면
  잔소리가 됩니다.
```

이를 아래로 교체한다:

```
  **사용자가 "3D/입체"라고 말하지 않았지만 재해위험(`disaster_risk`
  또는 레이어별 5개)을 역 하나에 대해 물어서 metric_distribution 또는
  explain_area 로 답한 경우, 그리고 위 자동 트리거 규칙이 조건을 만족하지
  못해 hazard_polygons를 부르지 않은 경우(즉 `disaster_risk`가
  strengths/weaknesses에 없는 경우), 답변 끝에 한 줄로 "원하시면 이 역
  주변을 3D로도 보여드릴 수 있어요" 정도로 짧게 제안합니다.**
  `residential_zone_ratio`를 물은 경우엔 explain_area라면 위 자동 트리거
  규칙이 이미 zoning_massing을 매번 부르므로 제안이 필요 없고,
  metric_distribution만으로 물은 경우에는 여전히 이 제안을 붙입니다. 그
  턴에 이미 hazard_polygons/zoning_massing 을 썼거나 사용자가 방금 3D를
  보고 난 뒤라면 또 제안하지 않습니다 — 매번 붙이면 잔소리가 됩니다.
```

- [ ] **Step 3: 문법·오탈자 확인**

Run: `cd backend && grep -n "explain_area 또는 rank_areas 1위" src/chika/interface/agent/prompts.py`
Expected: 방금 삽입한 불릿의 첫 줄이 정확히 한 번 출력된다.

Run: `cd backend && uv run python -c "import chika.interface.agent.prompts"`
Expected: 에러 없이 임포트된다(삼중따옴표 문자열 안에 이스케이프 안 된
백틱/따옴표가 없다는 최소 확인 — 이 파일은 순수 문자열 상수라 그 외의
문법 오류는 나지 않는다).

- [ ] **Step 4: 기존 테스트 스위트가 깨지지 않았는지 확인**

Run: `cd backend && uv run pytest`
Expected: 이 태스크가 프롬프트 문자열만 바꿨으므로 기존 테스트 전부
그대로 통과한다(이 문자열을 직접 검사하는 테스트는 없다 — `tests/`
안에 `prompts.py`를 import 문자열 비교로 테스트하는 파일이 없음을
`grep -rn "ANALYSIS_INSTRUCTIONS" backend/tests/`로 사전에 확인해도
좋다. 있다면 그 테스트가 깨지지 않는지 확인한다).

- [ ] **Step 5: 커밋**

```bash
git add backend/src/chika/interface/agent/prompts.py
git commit -m "feat(agent): explain_area/rank_areas 1위 결과에 대한 자동 3D 트리거 규칙 추가"
```

---

### Task 2: 실제 채팅으로 수동 검증

**Files:** 없음(코드 변경 없음 — 검증만).

**Interfaces:**
- Consumes: Task 1이 수정한 프롬프트가 반영된 백엔드 서버.

- [ ] **Step 1: 백엔드 서버 기동**

```bash
cd backend && .venv/bin/uvicorn chika.interface.api.app:app --host 127.0.0.1 --port 8000 --app-dir src
```

`.env`에 `OPENAI_API_KEY`가 이미 설정돼 있어야 한다(이 세션에서 이미
설정된 상태 — 새로 만들 필요 없음).

- [ ] **Step 2: 재해위험이 극단적인 역 — hazard_polygons 자동 호출 확인**

curl로 직접 `/chat`에 물어 SSE 이벤트를 확인한다(채팅 UI를 거치지 않아
LLM의 자연어 해석 편차 없이 툴 이름을 바로 확인할 수 있다):

```bash
curl -s -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"verify-hazard-1","message":"新宿駅 살기 좋아?"}' \
  | grep -o '"tool": "[a-z_]*"'
```

Expected: `explain_area` 호출 이후, 新宿駅의 `disaster_risk`가 실제로
극단적이면(이전 세션에서 新宿駅 안전 순위 백분위 91.7~97.9로 확인됨 —
상위권이라 `strengths`에 들어갈 가능성이 높다) `hazard_polygons`와
`zoning_massing`이 함께 출력에 나타나야 한다. `disaster_risk`가
`strengths`/`weaknesses`에 없는 역이면 `zoning_massing`만 나타나야
정상이다 — 두 경우 모두 `zoning_massing`은 반드시 나타나야 한다(조건
없이 매번 포함).

- [ ] **Step 3: 공원/학교 관련 지표가 두드러진 역 — park_polygons/school_facilities 확인**

```bash
curl -s -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"verify-park-school-1","message":"光が丘 살기 좋아?"}' \
  | grep -o '"tool": "[a-z_]*"'
```

光が丘는 이 세션 초반 조사에서 "공원 백분위 99.2, 카페 9.3"으로 확인된
극단적인 프로필이다 — `explain_area`의 `strengths`에 `park`가 들어갈
가능성이 매우 높다. Expected: `explain_area` 다음에 `park_polygons`와
`zoning_massing`이 나타난다. `elementary_school`/`middle_school`/
`childcare_education`이 光が丘의 strengths/weaknesses에 있다면
`school_facilities`도 함께 나타나야 한다.

- [ ] **Step 4: rank_areas 1위만 3D가 붙는지 확인**

```bash
curl -s -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"verify-rank-1","message":"한식당이 많고 조용한 동네를 찾고 있어요"}' \
  > /tmp/rank_verify.txt
grep -o '"tool": "[a-z_]*"' /tmp/rank_verify.txt
```

Expected: `rank_areas`(또는 `set_criteria` 뒤 랭킹 툴) 호출 이후, 1위
역의 `top_drivers`에 해당하는 조건(`park`/`disaster_risk`/학교 관련
메트릭)이 있으면 그 3D 툴이 자동으로 뒤따라 호출된다. 이때 **2위 이하
역에 대해서는 어떤 3D 툴도 호출되지 않아야 한다** — 응답 안에서 3D 툴
호출이 정확히 1위 역의 `station_id`/좌표에 대해서만 일어나는지
`/tmp/rank_verify.txt`의 `hazard_polygons`/`park_polygons`/
`school_facilities`/`zoning_massing` 이벤트의 `result` 안 `station_id`
또는 `lat`/`lon`을 1위 역의 것과 대조해 확인한다.

- [ ] **Step 5: 같은 역 재질문 시 재트리거 억제 확인**

```bash
curl -s -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"verify-suppress-1","message":"新宿駅 살기 좋아?"}' \
  | grep -o '"tool": "[a-z_]*"'
echo "=== 같은 세션, 후속 질문 ==="
curl -s -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"verify-suppress-1","message":"가격은 어때?"}' \
  | grep -o '"tool": "[a-z_]*"'
```

Expected: 두 번째 호출에서 첫 턴에 이미 자동 호출됐던 3D 툴(예:
`zoning_massing`)이 다시 나타나지 않는다. (이 규칙은 에이전트의 대화
맥락 기억에 의존하므로, LLM이 가끔 다르게 판단할 수 있다 — 반복
관찰해서 대체로 억제되는지를 본다. 한 번 재호출됐다고 바로 실패로
보지 않는다. 매번 재호출된다면 Task 1로 돌아가 프롬프트 문구를
강화한다.)

- [ ] **Step 6: 조건을 만족 못하는 경우 — 기존 제안 문구 확인**

`disaster_risk`가 극단적이지 않은 역(위 Step에서 안 걸린 역 아무거나,
또는 metric_distribution으로 먼저 `disaster_risk`가 중간권임을 확인한
역)에 대해 "○○역 살기 좋아?"를 물어, `hazard_polygons`가 자동 호출되지
않았다면 답변 텍스트 끝에 "원하시면 3D로도 보여드릴 수 있어요" 계열의
제안 문장이 실제로 붙는지 확인한다(텍스트 이벤트를 모아 확인 —
`grep -o '"delta": "[^"]*"'` 로 delta 조각을 이어붙여 읽는다).

- [ ] **Step 7: 결과 보고**

Step 2-6의 결과(통과/실패)를 정리해 보고한다. 실패가 있으면 Task 1의
프롬프트 문구를 조정하고 재검증한다 — 이 태스크 자체는 코드를 고치지
않는다.
