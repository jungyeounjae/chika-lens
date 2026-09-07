#!/usr/bin/env bash
# backend/.env 를 읽고, Maps 키는 gcloud 로 조회한다.
#
#   source scripts/load-env.sh
#
# 키 값을 출력하지 않는다 — 셸 히스토리와 터미널 스크롤백에 남지 않게.

_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

if [ -f "$_here/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$_here/.env"
  set +a
  echo "backend/.env 로드됨"
else
  echo "backend/.env 가 없다. cp .env.example .env 로 만든다." >&2
fi

# Maps 키가 비어 있으면 gcloud 에서 가져온다.
if [ -z "${GOOGLE_MAPS_API_KEY:-}" ]; then
  _key_name="projects/164536703483/locations/global/keys/32c7ed3d-bf75-4d2a-9b3c-c1ada799d513"
  GOOGLE_MAPS_API_KEY=$(curl -s \
    -H "Authorization: Bearer $(gcloud auth print-access-token 2>/dev/null)" \
    "https://apikeys.googleapis.com/v2/${_key_name}/keyString" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('keyString',''))" 2>/dev/null)
  export GOOGLE_MAPS_API_KEY
  unset _key_name
fi

for _v in OPENAI_API_KEY GOOGLE_MAPS_API_KEY; do
  if [ -n "${!_v:-}" ]; then
    echo "  $_v: 설정됨 (${#_v} 자 이름, 값 길이 $(eval echo \${#$_v}))"
  else
    echo "  $_v: 미설정"
  fi
done
unset _v _here
