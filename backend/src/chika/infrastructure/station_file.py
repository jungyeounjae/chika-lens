"""역 마스터 JSON 파일 어댑터. Phase 2에서 BigQuery 어댑터가 지표를 채운다."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from chika.domain.model.metrics import RawMetrics
from chika.domain.model.station import Station


class StationFileRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def stations(self) -> Sequence[Station]:
        if not self._path.exists():
            raise FileNotFoundError(f"station master not found: {self._path}")
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return [
            Station(
                id=row["id"],
                name_ja=row["name_ja"],
                name_ko=row["name_ko"],
                ward=row["ward"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                lines=tuple(row["lines"]),
            )
            for row in payload
        ]

    def raw_metrics(self) -> Sequence[RawMetrics]:
        """Phase 0에서는 지표가 없다. Phase 2의 BigQuery 어댑터가 채운다."""
        return []
