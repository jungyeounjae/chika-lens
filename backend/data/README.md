# data/

## `stations.json` — 도쿄 23구 역 마스터 (489개)

`chika.etl.build_stations` 산출물. 결정적(역 id 오름차순 정렬)이므로 커밋해 둔다.
매번 40MB짜리 원본을 다시 받을 이유가 없고, 모든 하위 작업이 이 파일에 의존한다.

**출처:** 国土数値情報（鉄道データ N02 令和4年版・行政区域データ N03 東京都）
国土交通省。[政府標準利用規約](https://nlftp.mlit.go.jp/ksj/other/agreement.html)에 따라
가공·재배포한다. 본 파일은 원본을 도쿄 23구로 필터링하고 역명 기준으로 병합한
가공물이며, 국토교통성이 작성한 것이 아니다.

### 재생성

```bash
# https://nlftp.mlit.go.jp/ksj/ 에서 최신 연도판을 받는다
#   N02: gml/data/N02/N02-<yy>/N02-<yy>_GML.zip  -> UTF-8/N02-<yy>_Station.geojson
#   N03: gml/data/N03/N03-<yyyy>/N03-<yyyymmdd>_13_GML.zip
uv run python -m chika.etl.build_stations \
    --n02 <N02_Station.geojson> --n03 <N03_13.geojson> --out data/stations.json
```

## `ward_stats.json` — 구 단위 통계 (커밋함)

`chika.etl.build_ward_stats` 산출물. 지표 3(구별 한국 국적 비율) 23구분.

**출처:** 東京都「区市町村、国籍・地域別外国人人口」および「住民基本台帳による
世帯と人口」（東京都総務局統計部）。東京都オープンデータ이며 政府標準利用規約에
따라 출처 표기 조건으로 재배포 가능하다 — 그래서 `metrics.json`과 달리 커밋한다.

원본 CSV 두 개를 수동으로 받아 실행한다:

```bash
curl -O https://www.toukei.metro.tokyo.lg.jp/gaikoku/2026/ga26ev0300.csv
curl -O https://www.toukei.metro.tokyo.lg.jp/juukim/2026/jm261v0000_1.csv
uv run python -m chika.etl.build_ward_stats \
    --foreign ga26ev0300.csv --population jm261v0000_1.csv
```

연 1회 갱신이면 충분하다 (원본이 매년 1월 1일 기준).

## `metrics.json` — 지표 인덱스 (커밋하지 않음)

`chika.etl.build_metrics` 산출물. 489역 × 지표별 원시값.

**커밋하지 않는다.** `stations.json`은 국토수치정보(출처 표기 조건으로 재배포 가능)라
커밋했지만, 이쪽은 **Google Maps 콘텐츠**다. 공개 저장소에 올리는 것은 재배포에
해당하고, 집계 수치에 30일 캐시 제한이 적용될 가능성도 있다. 출처가 다르면
취급도 달라야 한다.

```bash
export GOOGLE_MAPS_API_KEY=...
uv run python -m chika.etl.build_metrics --core --dry-run   # 콜 수만 계산
uv run python -m chika.etl.build_metrics --core             # 4,401콜 (월 1회)
uv run python -m chika.etl.build_metrics --diversity        # 3,912콜 (6개월 1회)
```

## `korean_shops.json` — 지표 2 (커밋하지 않음)

`chika.etl.build_korean_shops` 산출물. Places API (New) Text Search 결과이므로
`metrics.json` 과 같이 Google Maps 콘텐츠다 — 커밋하지 않는다.

```bash
export GOOGLE_MAPS_API_KEY=...
uv run python -m chika.etl.build_korean_shops --dry-run
uv run python -m chika.etl.build_korean_shops     # 489콜, 1회성
```

식자재점 분포는 달마다 바뀌지 않으므로 매월 돌릴 이유가 없다.

## `.cache/aggregate_progress.jsonl` — 배치 체크포인트 (커밋하지 않음)

조회 한 건마다 append된다. 배치가 중간에 죽어도 같은 명령을 다시 실행하면
남은 것부터 이어받는다. 부트스트랩이 8,313콜이고 무료 한도가 월 5,000콜이라
실패한 배치를 처음부터 다시 돌릴 여유가 없다.


현재 19/489(4%)만 채워져 있고 나머지는 `name_ja`로 폴백된다.
한국인 대상 서비스의 기본 표기가 일본어가 되므로 Phase 1 안에 채워야 한다.
