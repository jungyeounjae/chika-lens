"""LookupLandmark 유스케이스 — 가장 가까운 역 계산 + 거리 상한 플래그."""

from __future__ import annotations

from chika.application.usecase.lookup_landmark import FAR_FROM_STATION_M, LookupLandmark
from chika.domain.model.landmark import LandmarkMatch
from chika.domain.model.station import Station
from chika.infrastructure.fake.repositories import FakeAreaMetricsRepository


class _FakeGeocoder:
    def __init__(self, matches: list[LandmarkMatch]) -> None:
        self._matches = matches
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> list[LandmarkMatch]:
        self.calls.append((query, limit))
        return self._matches


def _station(station_id: str, lat: float, lon: float) -> Station:
    return Station(id=station_id, name_ja=station_id, ward="新宿区", lat=lat, lon=lon, lines=())


def test_finds_the_nearest_station_for_each_match() -> None:
    # 新宿御苑 근처: a는 도보권, b는 (Station의 도쿄 bbox 안에서) 훨씬 멀다.
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository(
        [_station("a", 35.6860, 139.7100), _station("b", 35.80, 139.80)], []
    )
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("신주쿠교엔")

    assert len(candidates) == 1
    assert candidates[0].nearest_station is not None
    assert candidates[0].nearest_station.station.id == "a"


def test_flags_far_from_any_station_beyond_the_cap() -> None:
    # 가장 가까운 역도 2,000m 훨씬 밖에 있도록(Station의 도쿄 bbox 안에서) 좌표를 벌린다.
    match = LandmarkMatch(name="외딴곳", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository([_station("a", 35.80, 139.80)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("외딴곳")

    assert candidates[0].nearest_station is not None
    assert candidates[0].nearest_station.distance_m > FAR_FROM_STATION_M
    assert candidates[0].far_from_any_station is True


def test_does_not_flag_a_station_within_the_cap() -> None:
    match = LandmarkMatch(name="新宿御苑", lat=35.6851, lon=139.7095)
    areas = FakeAreaMetricsRepository([_station("a", 35.6860, 139.7100)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([match]))

    candidates = usecase.execute("신주쿠교엔")

    assert candidates[0].far_from_any_station is False


def test_returns_an_empty_list_when_the_geocoder_finds_nothing() -> None:
    areas = FakeAreaMetricsRepository([_station("a", 35.68, 139.70)], [])
    usecase = LookupLandmark(areas, _FakeGeocoder([]))

    assert usecase.execute("존재하지 않는 곳") == []


def test_passes_the_query_and_max_matches_limit_to_the_geocoder() -> None:
    areas = FakeAreaMetricsRepository([_station("a", 35.68, 139.70)], [])
    geocoder = _FakeGeocoder([])
    usecase = LookupLandmark(areas, geocoder)

    usecase.execute("신주쿠교엔")

    assert geocoder.calls == [("신주쿠교엔", 3)]
