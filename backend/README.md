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

## API 서버 (Phase 4)

    export OPENAI_API_KEY=...
    uv sync --extra agent --extra api
    uv run python -m chika.interface.api

`POST /chat` 이 SSE 스트림을 돌려준다 — `tool` / `text` / `done` / `error`.
툴 결과가 텍스트보다 먼저 나가므로 프론트가 지도를 먼저 그릴 수 있다.

**여기서 처음으로 OpenAI 비용이 발생한다.** IP당 속도 제한(`CHIKA_RATE_PER_MIN`,
기본 6/분)과 일일 상한(`CHIKA_DAILY_CAP`, 기본 200)이 기본으로 걸려 있고,
거절된 요청은 에이전트를 돌리지 않는다.

`GET /healthz` 로 남은 일일 예산과 활성 세션 수를 볼 수 있다.
