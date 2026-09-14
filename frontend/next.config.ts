import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // React 18 StrictMode는 개발 모드에서 effect를 마운트→클린업→재마운트로
  // 두 번 실행한다. maplibre-gl 같은 명령형 라이브러리는 그 사이 지도를
  // 만들고 곧바로 remove() 했다가 같은 컨테이너에 다시 만드는 과정에서
  // 내부 상태가 꼬여 'load'/'styledata' 이벤트가 영영 안 온다(실측 —
  // 래스터 타일은 어찌어찌 그려지지만 pitch·커스텀 레이어는 전부 무효화됨).
  // 프로덕션에는 영향 없는 개발 전용 진단 기능이라 끈다.
  reactStrictMode: false,
};

export default nextConfig;
