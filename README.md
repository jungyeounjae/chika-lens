# Chika Lens

도쿄에서 한국인을 위한 생활 입지 분석 & 대화형 추천 에이전트

## 개요

Google Places Insights(BigQuery)와 일본 공공데이터를 활용하여 도쿄 역세권을
한국인 관점으로 정량 평가하고, OpenAI Agents SDK 기반 대화형 에이전트로
지역 추천을 제공합니다.

- **범위**: 도쿄 23구
- **성격**: 학습·포트폴리오 프로토타입
- **스택**: Python(에이전트·분석) + Next.js(채팅·지도) + BigQuery

## 구조

```
docs/superpowers/specs/  설계 문서
backend/                 Python 에이전트 + FastAPI
frontend/                Next.js 채팅 인터페이스
```

## 설계 문서

- [2026-09-03-chika-lens-design.md](docs/superpowers/specs/2026-09-03-chika-lens-design.md)

## 다음 단계

1. GCP 개인 프로젝트 설정
2. Places Insights 샘플 데이터 신청
3. ~~Phase 0: 도메인 모델 + 스코어링 구현~~ — 완료. 계획: [2026-09-03-chika-lens-phase0.md](docs/superpowers/plans/2026-09-03-chika-lens-phase0.md)
