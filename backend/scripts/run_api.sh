#!/usr/bin/env bash
# .env 를 읽어 API 서버를 띄운다 (launch.json 의 backend 설정용).
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$_here"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

exec uv run python -m chika.interface.api
