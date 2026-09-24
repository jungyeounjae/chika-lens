# Chika Lens Frontend

Next.js 15 채팅 인터페이스 — [백엔드](../backend)의 SSE `/chat` 엔드포인트에
붙어서, 텍스트 답변과 3D 지도 시각화를 동시에 렌더링합니다.

## 개발

```bash
npm install
npm run dev
```

[http://localhost:3000](http://localhost:3000) 접속. 백엔드가
`http://127.0.0.1:8000`에서 같이 떠 있어야 합니다(`../backend/README.md`
참고). API 주소는 `NEXT_PUBLIC_API_BASE` 환경변수로 바꿀 수 있습니다
(기본값 `http://127.0.0.1:8000`).

```bash
npm run lint    # eslint
npm run build   # 프로덕션 빌드 (타입체크 겸함)
```

## 구조

```
src/app/page.tsx              채팅 UI, SSE 이벤트 처리 (tool/text/done/error)
src/lib/chatStream.ts         SSE 스트림 파싱
src/lib/types.ts              백엔드 응답 타입
src/components/AreaMap.tsx    MapLibre GL 지도, 오버레이 관리
src/components/*ThreeLayer.ts Three.js 커스텀 레이어(3D 압출/마커 렌더링)
  - polygonThreeLayer.ts        재해위험·용도지역·공원 Polygon 압출
  - facilityThreeLayer.ts       학교/보육시설 마커
  - metricThreeLayer.ts         역 지표 막대
  - domeScanLayer.ts            선택된 역 강조(돔+스캐닝 링)
src/components/ChatMarkdown.tsx 어시스턴트 답변 마크다운 렌더링(GFM 표 포함)
```

지도 위 3D 오버레이는 `hazard`/`zoning`/`park`/`facilities` 여러 종류가
한 턴에 동시에 뜰 수 있습니다(`AreaMap`의 `Overlay[]` 상태).

## 스택

Next.js 15 · React 19 · MapLibre GL · Three.js · Tailwind CSS
