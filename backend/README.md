# Chika Lens Backend

## 개발

    uv sync
    uv run pytest
    uv run ruff check .
    uv run mypy src

## 계층 규칙

- `domain` — 표준 라이브러리만. 외부 패키지 import 금지.
- `application` — `domain` 만 import.
- `infrastructure` / `interface` — 자유. 단 `domain` 을 향해서만 의존한다.

## Phase 0 데모

    uv run python -m chika.interface.cli

시드 데이터로 "조건 → 랭킹 → 근거"가 끝까지 도는 것을 확인한다. OpenAI 키가 필요 없다.

## 역 마스터 생성

    uv run python -m chika.etl.build_stations --n02 <N02.geojson> --n03 <N03.geojson>

국토수치정보 GeoJSON은 https://nlftp.mlit.go.jp/ksj/ 에서 수동으로 받는다.
