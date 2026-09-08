/** 백엔드 SSE 이벤트. `backend/src/chika/interface/api/events.py` 와 짝을 이룬다. */

export type MetricDriver = {
  metric: string;
  /** 원시값의 단위. 전부 개수가 아니다 — "엔/㎡", "%", "종"이 섞여 있다. */
  unit: string;
  contribution: number;
  percentile: number;
  top_percent: number;
  is_ward_resolution: boolean;
  is_missing: boolean;
  /** 값을 오해할 여지가 있는 지표의 주의문. 없으면 null. */
  caveat: string | null;
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
  missing_metrics: string[];
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
  missing_metrics: string[];
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

export type ChatEvent =
  | { kind: "text"; delta: string }
  | { kind: "tool"; tool: string; result: unknown }
  | { kind: "done"; remainingToday: number }
  | { kind: "error"; code: string; message: string };
