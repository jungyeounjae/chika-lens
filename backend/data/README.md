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

## `station_name_ko.json` — 한국어 역명 대응표

현재 19/489(4%)만 채워져 있고 나머지는 `name_ja`로 폴백된다.
한국인 대상 서비스의 기본 표기가 일본어가 되므로 Phase 1 안에 채워야 한다.
