# Phase 0 인수인계 — Phase 1로 넘기는 것들

- 작성일: 2026-09-03
- 대상 브랜치: `phase-0-implementation` (main에 병합 완료)
- 계획: [2026-09-03-chika-lens-phase0.md](2026-09-03-chika-lens-phase0.md)
- 스펙: [../specs/2026-09-03-chika-lens-design.md](../specs/2026-09-03-chika-lens-design.md)

Phase 0 실행 중 내려진 판정과, 최종 전체 브랜치 리뷰가 Phase 1로 넘긴 항목들이다.
근거는 git 히스토리에 남아 있고, 이 문서는 "왜 그렇게 됐는지"와 "다음에 뭘 해야 하는지"만 담는다.

## 1. 미충족 종료 기준 (유일)

**`data/stations.json` — 실제 도쿄 23구 역 마스터 약 250개가 없다.**

국토수치정보 N02(철도)·N03(행정구역) GeoJSON은 일본어 포털에서 수동 다운로드가
필요해 Phase 0 세션이 가져올 수 없었다. 파서(`chika.etl.station_master`)와
CLI(`chika.etl.build_stations`)는 완성됐고 인라인 픽스처로 테스트됐지만,
**실제 파일로는 한 번도 검증되지 않았다.**

Phase 1 첫 작업:

```bash
# https://nlftp.mlit.go.jp/ksj/ 에서 N02 최신 연도판, N03 東京都판을 받은 뒤
cd backend && uv run python -m chika.etl.build_stations \
    --n02 <N02.geojson> --n03 <N03-tokyo.geojson> --out data/stations.json
```

결과가 200~350건이면 정상. 0건이나 1000건 초과면 `TOKYO_23_WARDS` 필터나
좌표 순서(GeoJSON은 `[lon, lat]`)를 먼저 의심한다.

**주의:** `StationFileRepository.raw_metrics()`가 `[]`를 반환하므로, 실역 마스터를
꽂는 순간 랭킹이 예외 없이 **조용히 빈 리스트**가 된다. Phase 1 첫날 이걸로
헤맬 가능성이 크다. `build_stations.py`에 "파싱 결과 0건이면 비정상 종료"를
넣어두는 편이 좋다.

## 2. 포트 두 개는 모양을 바꿔야 한다 (N+1)

최종 리뷰 지적. 지금 고치면 Fake 2개와 유스케이스 1곳만 손대면 되지만,
실제 어댑터를 쓴 뒤에 고치면 비용이 커진다.

| 포트 | 현재 | 문제 | 권장 |
|---|---|---|---|
| `PriceRepository.median_rent_yen(station_id, household)` | 역마다 1회 | 랭킹 루프 안에서 최대 250회 순차 호출 → MLIT 어댑터에서 250 라운드트립 | `median_rents(household) -> Mapping[str, int \| None]` 배치 |
| `CommuteRepository.minutes_to(origin, dest)` | 역마다 1회 | 동일 | `minutes_from_all(dest) -> Mapping[str, int]` |

`AreaMetricsRepository.raw_metrics()`는 **지금 모양이 맞다.** 쿼리 파라미터가
없는 것은 결함이 아니라 "퍼센타일은 필터 이전 전체 모집단에서 계산한다"는
설계 제약의 필연이다. 250역 × 15지표 = 약 3,750 float은 BigQuery 한 번이면 끝난다.

## 3. 캐싱 계층이 없다

`RankAreas` / `ExplainArea` / `CompareAreas`가 **각각** `raw_metrics()` + `normalize()`를
호출한다. 대화 한 턴에 랭킹 → 설명 → 비교가 이어지면 전수 쿼리 3회 + 정규화 3회다.
파일에서 읽는 Phase 0에서는 무시할 만하지만 BigQuery에서는 아니다.

포트 시그니처는 그대로 두고, 어댑터에 메모이제이션을 넣거나 정규화된 인덱스를
한 번 만들어 주입하는 층을 Phase 1에 추가한다.

## 4. 없는 포트: 역 이름 해석

`act_set_criteria`가 지금은 `UseCases`를 통해 역 목록을 훑어 이름→id를 해석한다.
Phase 1에서 역이 250개가 되고 별칭("신주쿠", "新宿", "Shinjuku")까지 다루려면
`StationLookup` 포트를 따로 두는 편이 낫다.

## 5. 지켜야 할 일관성 계약 (코드에 없음)

**예산 필터가 쓰는 `PriceRepository` 값과 `MetricKey.PRICE_LEVEL` 퍼센타일은
Phase 1에서 같은 MLIT 소스에서 나와야 한다.** 시드는 의도적으로 같은 값을
쓰지만(`seed.py`), 이 계약이 코드에도 테스트에도 적혀 있지 않다.

갈라지면 "예산 안에 들어온 역인데 시세 감점이 크다"는 모순이 화면에 나온다.
Phase 1에서 어댑터를 만들 때 이걸 강제하는 테스트를 함께 넣는다.

## 6. Phase 0에서 내린 판정 8건

계획을 코드로 옮기는 과정에서 계획 자체의 결함이 드러나 판정한 것들이다.

| # | 무엇 | 판정 | 틀렸을 때의 비용 |
|---|---|---|---|
| 1 | 계획의 누적 테스트 개수가 실제보다 1 낮음 (Task 1의 `test_package.py` 누락) | 개수는 게이트가 아닌 참고치 | 낮음 |
| 2 | `importorskip("agents")`가 스킵될 가능성 | 스킵돼도 Task 11 완료 인정 | 해소됨 — SDK 설치되어 4개 전부 실행 |
| 3 | Task 10 실데이터 다운로드 불가 | 사전 승인, Phase 1로 보류 | 낮음 — 위 §1 |
| 4 | 계획의 테스트 한 줄이 자신이 정한 ruff 100자 초과 | 줄바꿈 | 없음 |
| 5 | 계획의 `station_master.py`가 `mypy --strict` 미통과 | 최소 타입 내로잉 허용 | 중간 — 감사 결과 역 누락 불가 확인 |
| 6 | 가중치 15개를 4자리 반올림해 놓고 합이 `1e-6` 내 1.0이길 요구 (구조적 통과 불가) | 반올림 유지, 허용오차 `1e-3` | 무시할 수준 — 표시용 |
| 7 | 아키텍처 가드를 상대 임포트가 전부 우회 | 즉시 차단 (상대 임포트 금지 테스트) | 사소 |
| 8 | 최종 리뷰 3건 (아래 §7) | 병합 전 일괄 수정 | 낮음 |

## 7. 최종 전체 브랜치 리뷰가 찾은 것 (수정 완료)

12개 태스크 리뷰 어느 것도 볼 수 없었던 교차 결함. 전부 수정됐지만, 왜 생겼는지는
Phase 1 설계에 참고가 된다.

1. **`act_rank_areas`가 정직성 플래그를 떨어뜨렸다.** 랭킹 페이로드에
   `is_ward_resolution`과 `missing`이 없어, 구 단위 지표가 라벨 없이 1위 근거로
   서술되고 결측 지표가 측정된 것처럼 서술될 수 있었다. **CLI/explain 경로에서는
   보장이 지켜지고 있었는데 에이전트 경로에서만 깨져 있었다** — 계층별 리뷰가
   놓치는 전형적 형태다.
2. **통근 하드 필터가 조용히 사라졌다.** LLM이 넣은 자연어 역명("신주쿠")이
   해석 없이 station_id로 쓰여 조회가 항상 실패했고, `None`은 "판단 보류"로
   통과됐다. 데이터 부재와 해석 실패가 구분되지 않은 것이 원인.
3. **아키텍처 가드가 자신이 지킨다고 적힌 것의 절반만 지켰다.** `application`의
   서드파티 임포트 미검사, `infrastructure`/`interface` 방향 미검사, 문자열 grep
   사용. 지금은 9개 테스트로 AST 기반 전수 검사한다.

## 8. 보류한 사소한 항목

우선순위 낮음. 건드릴 일이 있을 때 함께 처리한다.

- `pyproject.toml`의 `etl` extra에 선언된 shapely/pyproj가 **전혀 쓰이지 않는다**
  (`station_master.py`는 순수 파이썬 ray casting). 락파일 무게의 실제 원인.
- 시드가 결측 시세를 130,000엔으로 지어내, `rent_yen is None` 경로를 어떤 테스트도
  밟지 않는다. `PRICE_LEVEL` 결측 역은 시세도 `None`이어야 결측 표기가 실제로 굴러간다.
- ETL이 역명 해시로만 병합한다. 23구 내 동명이역은 하나로 합쳐지고, 구는 먼저 만난
  피처 것이 채택된다. `id`가 역명에 종속돼 있어 표기가 바뀌면 조인 키가 어긋난다.
- `data/station_name_ko.json`이 20개뿐이다. 250역을 파싱하면 나머지 약 230개의
  `name_ko`가 일본어로 채워진다 — "한국인용" 화면의 기본 표기가 일본어가 된다.
- `VALUE_GAP_DISCLAIMER`가 정의만 되고 쓰이지 않는다. 스펙 §5.3-2의 "면책 문구
  강제 삽입"이 실제로는 강제되지 않는다 (가치 갭은 Phase 3).
- `ExplainArea.execute`가 호출마다 O(n) 선형 스캔 2회. 250역에서는 무의미하나,
  위 §3의 캐싱과 함께 잡으면 된다.
- `percentile`과 `top_percent`를 각각 반올림해 `.x5` 경계에서 0.1 어긋날 수 있다. 표시용.
- ruff `banned-api`의 pydantic 금지가 리포 전역이다. 메시지는 "interface 계층에서만
  사용"이라지만 규칙에 계층 예외가 없다.

## 9. OpenAI API 키

**Phase 4까지 필요 없다.** 현재 코드는 `Runner.run()`을 호출하지 않고
`OPENAI_API_KEY`를 읽지도 않는다. 121개 테스트와 데모 CLI 전부 키 없이 돈다.
점수 계산이 순수 함수이고 LLM은 앞뒤 번역만 하기 때문이다.
