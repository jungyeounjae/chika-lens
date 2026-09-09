# Chika Lens

도쿄에서 한국인을 위한 생활 입지 분석 & 대화형 추천 에이전트

## 개요

Google Places Aggregate API·国土交通省 不動産情報ライブラリ(MLIT)·일본 공공데이터를
활용하여 도쿄 역세권을 한국인 관점으로 정량 평가하고, OpenAI Agents SDK 기반
대화형 에이전트로 지역 추천을 제공합니다.

- **범위**: 도쿄 23구
- **성격**: 학습·포트폴리오 프로토타입
- **스택**: Python(에이전트·분석) + Next.js(채팅·지도)

## 구조

```
docs/superpowers/specs/  설계 문서
backend/                 Python 에이전트 + FastAPI
frontend/                Next.js 채팅 인터페이스
```

## 설계 문서

- [2026-09-03-chika-lens-design.md](docs/superpowers/specs/2026-09-03-chika-lens-design.md)

## 남은 일

설계서 [§11 미결 사항](docs/superpowers/specs/2026-09-03-chika-lens-design.md)이
단일 출처다 — 여기서 목록을 따로 유지하지 않는다.
