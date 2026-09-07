"""파일 기반 지표 리포지토리.

런타임은 API를 부르지 않는다. Aggregate 배치가 인덱스 파일을 만들고,
여기서는 읽기만 한다 — 퍼센타일은 필터 이전 전체 모집단에서 계산해야 하므로
어차피 매번 전수 로딩이고, 489역 × 15지표는 수십 KB에 불과하다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from chika.domain.model.metrics import MetricKey, RawMetrics
from chika.domain.model.station import Station


class FileAreaMetricsRepository:
    """`stations.json` + `metrics.json`을 읽어 `AreaMetricsRepository`를 구현한다."""

    def __init__(
        self,
        stations_path: Path,
        metrics_path: Path,
        ward_stats_path: Path | None = None,
    ) -> None:
        self._stations_path = stations_path
        self._metrics_path = metrics_path
        self._ward_stats_path = ward_stats_path

    def stations(self) -> Sequence[Station]:
        rows = self._load(self._stations_path, "station master")
        return [
            Station(
                id=row["id"],
                name_ja=row["name_ja"],
                ward=row["ward"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                lines=tuple(row["lines"]),
            )
            for row in rows
        ]

    def raw_metrics(self) -> Sequence[RawMetrics]:
        """지표 인덱스. 파일이 없으면 조용히 비우지 않고 시끄럽게 실패한다.

        빈 리스트를 돌려주면 랭킹이 예외 없이 빈 결과가 되어, 원인 표시 없이
        디버깅에 시간을 버리게 된다.
        """
        index = self._load(self._metrics_path, "metrics index")
        ward_stats = self._load_optional(self._ward_stats_path)
        return [
            RawMetrics(
                station_id=station.id,
                values=self._values(
                    ward_stats.get(station.ward, {}),
                    index.get(station.id, {}),
                ),
            )
            for station in self.stations()
        ]

    @staticmethod
    def _values(*rows: dict[str, float]) -> dict[MetricKey, float | None]:
        """뒤에 오는 row가 앞을 덮는다 — 역 단위 값이 구 단위 값보다 정확하다."""
        values: dict[MetricKey, float | None] = dict.fromkeys(MetricKey, None)
        for row in rows:
            for name, value in row.items():
                try:
                    key = MetricKey(name)
                except ValueError:
                    # 지표 정의가 바뀌어도 옛 인덱스가 로딩을 죽이면 안 된다.
                    continue
                values[key] = float(value)
        return values

    @staticmethod
    def _load_optional(path: Path | None) -> dict:  # type: ignore[type-arg]
        """구 단위 통계는 선택이다 — 없어도 나머지 지표로 랭킹은 돌아야 한다."""
        if path is None or not path.exists():
            return {}
        loaded: dict = json.loads(path.read_text(encoding="utf-8"))  # type: ignore[type-arg]
        return loaded

    @staticmethod
    def _load(path: Path, what: str) -> dict:  # type: ignore[type-arg]
        if not path.exists():
            raise FileNotFoundError(f"{what} not found: {path}")
        loaded: dict = json.loads(path.read_text(encoding="utf-8"))  # type: ignore[type-arg]
        return loaded
