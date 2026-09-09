"""XKT015(駅別乗降客数) 파싱·집계 — 대표 레코드 판별과 SUM 집계가 핵심."""

from __future__ import annotations

import pytest

from chika.etl.mlit_ridership import (
    RidershipShapeError,
    aggregate_by_group,
    parse_all,
    parse_ridership,
)


def _feature(
    group: str = "003700",
    name: str = "新宿",
    representative: str = "1",
    value: float = 1_000.0,
    coords: list[list[float]] | None = None,
) -> dict[str, object]:
    coords = coords or [[139.700, 35.690], [139.702, 35.692]]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "S12_001_ja": name,
            "S12_001g": group,
            "S12_054": representative,
            "S12_057": str(value),
        },
    }


def test_parses_the_representative_flag_and_value() -> None:
    point = parse_ridership(_feature(representative="1", value=1_301_204.0), year=2023)
    assert point.is_representative is True
    assert point.value == 1_301_204.0
    assert point.group_code == "003700"


def test_a_duplicate_record_is_flagged_not_representative() -> None:
    point = parse_ridership(_feature(representative="2", value=0.0), year=2023)
    assert point.is_representative is False


def test_the_centroid_is_the_coordinate_average() -> None:
    point = parse_ridership(_feature(coords=[[139.0, 35.0], [139.2, 35.2]]))
    assert point.lat == pytest.approx(35.1)
    assert point.lon == pytest.approx(139.1)


def test_missing_value_field_fails_loudly() -> None:
    feature = _feature()
    del feature["properties"]["S12_057"]  # type: ignore[index]
    with pytest.raises(RidershipShapeError, match="S12_057"):
        parse_ridership(feature, year=2023)


def test_aggregate_sums_representative_records_not_max() -> None:
    """신주쿠처럼 사업자가 여럿이면 대표 레코드도 여럿이다 — MAX 를 쓰면
    가장 큰 사업자 하나만 남아 다사업자 환승역을 실제보다 적게 계산한다."""
    points = parse_all(
        [
            _feature(group="003700", representative="1", value=1_301_204.0),  # JR
            _feature(group="003700", representative="1", value=439_840.0),  # 오다큐
            _feature(group="003700", representative="2", value=0.0),  # JR 야마노테 (중복)
        ],
        year=2023,
    )
    groups = aggregate_by_group(points)
    assert len(groups) == 1
    assert groups[0].total == pytest.approx(1_301_204.0 + 439_840.0)


def test_aggregate_drops_non_representative_records() -> None:
    points = parse_all([_feature(representative="2", value=999.0)], year=2023)
    assert aggregate_by_group(points) == []


def test_aggregate_anchor_is_the_average_of_representative_coords() -> None:
    """品川역 재현: 신칸센 홈이 재래선보다 역 좌표에서 훨씬 멀리 떨어져
    있다. 첫 레코드만 앵커로 쓰면 매칭이 반경 밖으로 밀릴 수 있어
    평균을 쓴다."""
    points = parse_all(
        [
            _feature(representative="1", value=71_078.0, coords=[[139.740, 35.630]]),  # 신칸센
            _feature(representative="1", value=548_442.0, coords=[[139.738, 35.628]]),  # 山手線
        ],
        year=2023,
    )
    groups = aggregate_by_group(points)
    assert len(groups) == 1
    assert groups[0].lat == pytest.approx((35.630 + 35.628) / 2)
    assert groups[0].lon == pytest.approx((139.740 + 139.738) / 2)


def test_aggregate_keeps_separate_groups_separate() -> None:
    points = parse_all(
        [
            _feature(group="003700", name="新宿", representative="1", value=100.0),
            _feature(group="003568", name="中野", representative="1", value=50.0),
        ],
        year=2023,
    )
    groups = {g.group_code: g.total for g in aggregate_by_group(points)}
    assert groups == {"003700": 100.0, "003568": 50.0}
