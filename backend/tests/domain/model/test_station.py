import pytest

from chika.domain.model.station import Station


def test_station_is_frozen() -> None:
    station = Station(
        id="nakano",
        name_ja="中野",
        name_ko="나카노",
        ward="中野区",
        lat=35.7056,
        lon=139.6659,
        lines=("JR中央線",),
    )
    with pytest.raises(AttributeError):
        station.ward = "新宿区"  # type: ignore[misc]


def test_station_rejects_coordinates_outside_tokyo() -> None:
    with pytest.raises(ValueError, match="outside Tokyo"):
        Station(
            id="busan",
            name_ja="釜山",
            name_ko="부산",
            ward="中野区",
            lat=35.1,
            lon=129.0,
            lines=(),
        )
