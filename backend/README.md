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
