import json
from pathlib import Path

import pytest

from chika.infrastructure.station_file import StationFileRepository


def _write(tmp_path: Path, payload: list[dict]) -> Path:
    path = tmp_path / "stations.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_loads_stations_from_json(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "id": "nakano",
                "name_ja": "中野",
                "ward": "中野区",
                "lat": 35.7056,
                "lon": 139.6659,
                "lines": ["中央線"],
            }
        ],
    )
    repo = StationFileRepository(path)
    stations = repo.stations()
    assert len(stations) == 1
    assert stations[0].name_ja == "中野"
    assert stations[0].lines == ("中央線",)


def test_raw_metrics_is_empty_until_phase_2(tmp_path: Path) -> None:
    repo = StationFileRepository(_write(tmp_path, []))
    assert list(repo.raw_metrics()) == []


def test_missing_file_raises_a_clear_error(tmp_path: Path) -> None:
    repo = StationFileRepository(tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="nope.json"):
        repo.stations()
