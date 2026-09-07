"""개발용 서버 기동.

    export OPENAI_API_KEY=...
    uv run python -m chika.interface.api

여기서 처음으로 OpenAI 비용이 발생한다. 대화 한 번에 수 센트 수준이며,
IP당 속도 제한과 일일 상한이 기본으로 걸려 있다 (스펙 §9).
"""

from __future__ import annotations

import os
import sys

import uvicorn

from chika.interface.api.app import create_app
from chika.interface.api.runner import run_turn


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        sys.exit("OPENAI_API_KEY 가 비어 있다. export 로 넘긴다.")
    uvicorn.run(
        create_app(run_turn),
        host=os.environ.get("CHIKA_HOST", "127.0.0.1"),
        port=int(os.environ.get("CHIKA_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
