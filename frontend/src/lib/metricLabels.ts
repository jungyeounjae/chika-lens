/** 지표 키 → 한국어 표기.
 *
 * 역명은 일본어 그대로 두지만(부동산 검색·발권에 쓰는 실용 문자열),
 * 지표 이름은 설명이므로 한국어로 옮긴다.
 */
export const METRIC_LABELS: Record<string, string> = {
  korean_restaurant: "한식당",
  korean_grocery: "한국 식자재점",
  korean_resident_ratio: "한국 국적 비율",
  supermarket: "슈퍼마켓",
  convenience_store: "편의점",
  healthcare: "의료·약국",
  cafe: "카페",
  park: "공원",
  fitness: "피트니스",
  restaurant_variety: "음식점 다양성",
  childcare_education: "보육·교육",
  child_friendly_venue: "아이 동반 시설",
  price_level: "시세",
  disaster_risk: "재해위험",
  nuisance_venue: "감점 상권",
};

export const metricLabel = (key: string): string => METRIC_LABELS[key] ?? key;
