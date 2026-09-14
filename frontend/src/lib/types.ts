/** 백엔드 SSE 이벤트. `backend/src/chika/interface/api/events.py` 와 짝을 이룬다. */

export type MetricDriver = {
  /** 내부 키. 화면에는 label 을 쓴다. */
  metric: string;
  /** 사람이 읽는 지표 이름. 백엔드 METRIC_LABELS_KO 가 유일한 정의처다. */
  label: string;
  /** 원시값의 단위. 전부 개수가 아니다 — "엔/㎡", "%", "종"이 섞여 있다. */
  unit: string;
  contribution: number;
  percentile: number;
  top_percent: number;
  is_ward_resolution: boolean;
  is_missing: boolean;
};

export type RankedArea = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  score: number;
  rent_yen: number | null;
  commute_minutes: number | null;
  commute_uncertain?: boolean;
  top_drivers: MetricDriver[];
  missing_metrics: MissingMetric[];
};

/** 결측 지표. 키만 오면 화면과 서술이 다른 이름을 쓰게 된다. */
export type MissingMetric = {
  metric: string;
  label: string;
};

/** `explain_area` 의 반환. 한 역을 지도에 표시하는 데 필요한 최소 필드. */
export type ExplainedArea = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  /** 랭킹 안의 역일 때만 온다. 비교 기준 없는 단일 조회에서는 백엔드가 뺀다
   *  (`backend/src/chika/interface/agent/actions.py` act_explain_area). */
  score?: number;
  score_omitted?: "no_reference_set";
  rent_yen: number | null;
  strengths: MetricDriver[];
  weaknesses: MetricDriver[];
  missing_metrics: MissingMetric[];
  nearby: NearbyStation[];
};

/** 주변 역. 좌표가 로컬에 있어 API 비용이 0이다. */
export type NearbyStation = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  lines: string[];
  distance_m: number;
};

/** 지도가 그릴 수 있는 최소 형태 — 랭킹이든 단일 조회든 같다.
 *  `score` 는 비교 기준 없는 단일 조회에서 없을 수 있다. */
export type MapPin = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  score?: number;
};

/** `metric_distribution` 결과 — 한 지표를 역 단위로 지도에 색칠할 재료.
 *
 * MLIT 원본 폴리곤(재해위험 등) 자체는 `hazard_polygons`/`zoning_massing`이
 * 따로 낸다(스펙 §3.1.2 정정, 2026-09-11 — PDL1.0이 출처 표기 조건으로
 * 허용한다) — 이 타입은 그 대신 우리가 정규화한 역 단위 percentile 이다.
 * `percentile` 은 항상 "높을수록 좋다/안전하다"로 통일돼 있다 — raw_value 의
 * 방향과 반대인 지표(시세·재해위험·감점 상권)가 있으니 색은 반드시
 * percentile로 매긴다.
 */
export type DistributionPoint = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  percentile: number;
  raw_value: number | null;
  is_missing: boolean;
  distance_m: number;
};

export type MetricDistribution = {
  metric: string;
  label: string;
  unit: string;
  is_ward_resolution: boolean;
  points: DistributionPoint[];
};

/** GeoJSON 좌표 — 서버가 MLIT 응답을 그대로 넘긴다(WGS84, [lon, lat]). */
export type GeoJsonGeometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };

/** `hazard_polygons` 결과 하나 — 홍수·토사재해·액상화·해일·쓰나미 5개 레이어의
 * 원본 Polygon.
 *
 * `metric_distribution`과 달리 MLIT 원본 구역 경계 그대로다(스펙 §3.1.2
 * 정정, 2026-09-11 — PDL1.0이 출처 표기 조건으로 허용). `label`은 실제
 * 침수深 구간("0.5m~3.0m") · Yellow/Red 존 · 액상화 등급 등이지 백분위가
 * 아니다.
 */
export type HazardPolygon = {
  layer: "flood" | "sediment" | "liquefaction" | "storm_surge" | "tsunami";
  geometry: GeoJsonGeometry;
  severity: number;
  label: string;
};

export type HazardPolygonResult = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  radius_m: number;
  attribution: string;
  polygons: HazardPolygon[];
};

/** `zoning_massing` 결과 하나 — 용도지역 원본 Polygon.
 *
 * `height_m`은 실제 법정 높이 제한이 아니라 저층/고밀 대비를 보여주는
 * 일러스트용 근사치다(backend `zoning_massing.py` 참고).
 */
export type ZoningPolygon = {
  geometry: GeoJsonGeometry;
  youto_id: number;
  use_area_ja: string;
  height_m: number;
};

export type ZoningMassingResult = {
  station_id: string;
  name_ja: string;
  ward: string;
  lat: number;
  lon: number;
  radius_m: number;
  attribution: string;
  polygons: ZoningPolygon[];
};

/** `school_facilities` 결과 하나 — 좌표 주변 학교/유치원/보육시설.
 *
 * station_id 가 없다 — 역이 아니라 좌표(신축 물건 등) 기준으로도 조회되기
 * 때문이다(backend `school_facilities.py` 참고).
 */
export type SchoolFacility = {
  facility_id: string;
  name: string;
  kind: string;
  lat: number;
  lon: number;
  distance_m: number;
};

export type SchoolFacilitiesResult = {
  lat: number;
  lon: number;
  radius_m: number;
  facilities: SchoolFacility[];
};

export type ChatEvent =
  | { kind: "text"; delta: string }
  | { kind: "tool"; tool: string; result: unknown }
  | { kind: "status"; text: string }
  | { kind: "done"; remainingToday: number }
  | { kind: "error"; code: string; message: string };
