import json
from pathlib import Path

import pytest

from chika.domain.model.metrics import MetricKey
from chika.infrastructure.file_metrics import FileAreaMetricsRepository

_STATION = {
    "id": "st_a", "name_ja": "中野", "ward": "中野区",
    "lat": 35.7056, "lon": 139.6659, "lines": ["中央線"],
}


def _write(tmp_path: Path, stations: list, metrics: dict | None) -> FileAreaMetricsRepository:
    sp = tmp_path / "stations.json"
    sp.write_text(json.dumps(stations, ensure_ascii=False), encoding="utf-8")
    mp = tmp_path / "metrics.json"
    if metrics is not None:
        mp.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
    return FileAreaMetricsRepository(sp, mp)


def test_loads_stations_and_metrics(tmp_path: Path) -> None:
    repo = _write(tmp_path, [_STATION], {"st_a": {"cafe": 12.0, "park": 3.0}})
    assert [s.name_ja for s in repo.stations()] == ["中野"]
    raws = repo.raw_metrics()
    assert raws[0].get(MetricKey.CAFE) == 12.0
    assert raws[0].get(MetricKey.PARK) == 3.0


def test_metrics_not_in_the_file_are_missing_not_zero(tmp_path: Path) -> None:
    """MLIT 담당 지표는 아직 없다. 0으로 채우면 '시세가 0엔'이 된다."""
    repo = _write(tmp_path, [_STATION], {"st_a": {"cafe": 12.0}})
    assert repo.raw_metrics()[0].get(MetricKey.PRICE_LEVEL) is None


def test_a_station_with_no_metrics_row_is_all_missing(tmp_path: Path) -> None:
    repo = _write(tmp_path, [_STATION], {})
    raw = repo.raw_metrics()[0]
    assert raw.station_id == "st_a"
    assert all(raw.get(key) is None for key in MetricKey)


def test_unknown_metric_keys_in_the_file_are_ignored(tmp_path: Path) -> None:
    """지표 정의가 바뀌어도 옛 인덱스 파일이 로딩을 죽이면 안 된다."""
    repo = _write(tmp_path, [_STATION], {"st_a": {"cafe": 1.0, "retired_metric": 9.0}})
    assert repo.raw_metrics()[0].get(MetricKey.CAFE) == 1.0


def test_station_order_is_preserved(tmp_path: Path) -> None:
    second = {**_STATION, "id": "st_b", "name_ja": "新宿"}
    repo = _write(tmp_path, [second, _STATION], {})
    assert [s.id for s in repo.stations()] == ["st_b", "st_a"]
    assert [r.station_id for r in repo.raw_metrics()] == ["st_b", "st_a"]


def test_missing_station_file_says_which_file(tmp_path: Path) -> None:
    repo = FileAreaMetricsRepository(tmp_path / "nope.json", tmp_path / "m.json")
    with pytest.raises(FileNotFoundError, match="nope.json"):
        repo.stations()


def test_missing_metrics_file_fails_loudly(tmp_path: Path) -> None:
    """조용히 빈 결과를 돌려주면 랭킹이 이유 없이 비어 디버깅에 시간을 버린다."""
    repo = _write(tmp_path, [_STATION], metrics=None)
    with pytest.raises(FileNotFoundError, match="metrics.json"):
        repo.raw_metrics()


def test_station_coordinates_are_validated(tmp_path: Path) -> None:
    outside = {**_STATION, "lat": 35.1, "lon": 129.0}
    repo = _write(tmp_path, [outside], {})
    with pytest.raises(ValueError, match="outside Tokyo"):
        repo.stations()
