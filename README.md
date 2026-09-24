# Chika Lens

도쿄에서 한국인을 위한 생활 입지 분석 & 대화형 추천 에이전트

## 개요

Google Places Aggregate API·国土交通省 不動産情報ライブラリ(MLIT)·OpenStreetMap·
일본 공공데이터를 활용하여 도쿄 23구 489개 역세권을 한국인 관점(한식·한인
밀집도, 육아 환경, 재해 안전성, 시세 등) 15개 지표로 정량 평가하고,
`openai-agents` SDK 기반 대화형 에이전트로 지역 추천과 3D 지도 시각화를
제공합니다.

- **범위**: 도쿄 23구
- **성격**: 학습·포트폴리오 프로토타입 (개인 사용 목적, 상용화 계획 없음)
- **스택**: Python 3.12(에이전트·분석, FastAPI+SSE) + Next.js 15(채팅·지도,
  MapLibre GL + Three.js)

## 주요 기능

- **조건 기반 랭킹** — "한식당 많고 조용한 동네", "신혼부부가 정착하기
  좋은 동네"처럼 자연어 조건을 다이얼(생활 편의/환경/육아/비용·위험 등)로
  해석해 순위를 매깁니다.
- **역 이름 · 랜드마크 검색** — 역 이름은 물론 "신주쿠교엔"처럼 역이 아닌
  지명으로 물어도 좌표를 찾아 가장 가까운 역 기준으로 분석합니다(역에서
  너무 멀면 그 사실을 알리고 되묻습니다).
- **자동 3D 시각화** — 질문 내용에 따라 재해위험·용도지역·학교/보육시설·
  공원 3D 시각화가 "3D로 보여줘"라고 말하지 않아도 자동으로 뜹니다.
- **신축 분양 물건 검색** — 구·가격·재해위험 등으로 필터링해 SUUMO 신축
  분양 정보를 찾아줍니다.

점수 계산은 전부 `application` 계층의 순수 함수이고, LLM은 조건 해석과
결과 서술만 담당합니다 — 같은 조건이면 몇 번을 물어도 점수 자체는 항상
같습니다.

## 구조

```
docs/superpowers/specs/  설계 문서 (기능별)
docs/superpowers/plans/  구현 계획 (기능별)
backend/                 Python 에이전트 + FastAPI
frontend/                Next.js 채팅 인터페이스
.github/workflows/       CI (백엔드 pytest/ruff/mypy, 프런트 eslint/build)
```

## 설계 문서

전체 아키텍처는 [2026-09-03-chika-lens-design.md](docs/superpowers/specs/2026-09-03-chika-lens-design.md)에서
시작합니다. 그 이후 추가된 기능들은 `docs/superpowers/specs/`에 기능별로
스펙 문서가 따로 있습니다(파일명 앞 날짜순으로 보면 진행 순서를 알 수
있습니다) — 예: 학교/보육시설 3D, OSM 공원 Polygon, 자동 3D 트리거, 다중
3D 레이어 통합, 랜드마크 검색 등. 단일 문서로 전부 관리하지 않습니다.

## 개발

```
cd backend && uv sync --all-extras
cd frontend && npm install
```

각 디렉토리의 README(`backend/README.md`, `frontend/README.md`)에 개발
서버 기동법이 있습니다.
