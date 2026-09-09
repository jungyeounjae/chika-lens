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
 * MLIT 원본 폴리곤(재해위험 등)은 지도에 그릴 수 없다(스펙 §3.1.2) — 이건
 * 그 대신 우리가 정규화한 역 단위 percentile 이다. `percentile` 은 항상
 * "높을수록 좋다/안전하다"로 통일돼 있다 — raw_value 의 방향과 반대인
 * 지표(시세·재해위험·감점 상권)가 있으니 색은 반드시 percentile로 매긴다.
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

export type ChatEvent =
  | { kind: "text"; delta: string }
  | { kind: "tool"; tool: string; result: unknown }
  | { kind: "done"; remainingToday: number }
  | { kind: "error"; code: string; message: string };
