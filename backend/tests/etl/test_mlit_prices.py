"""지표 13(시세) 파싱과 집계. 실측 포맷을 그대로 쓴다."""

from __future__ import annotations

import pytest

from chika.etl.mlit_prices import (
    MIN_SAMPLES,
    Transaction,
    TransactionShapeError,
    median_unit_price_near,
    parse_all,
    parse_area,
    parse_transaction,
    parse_yen,
    quarter_range,
)

SHINJUKU = (35.6938, 139.7036)


def _feature(
    price: str = "3,200万円",
    area: str = "20㎡",
    land_type: str = "中古マンション等",
    lat: float = SHINJUKU[0],
    lon: float = SHINJUKU[1],
    quarter: str = "2025年第3四半期",
    **extra: object,
) -> dict[str, object]:
    return {
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "land_type_name_ja": land_type,
            "u_transaction_price_total_ja": price,
            "u_area_ja": area,
            "point_in_time_name_ja": quarter,
            **extra,
        },
    }


# --- 값 파싱 ---


def test_price_is_parsed_from_the_manyen_format() -> None:
    """실측에서 총액은 전부 "N,NNN万円" 계열 하나였다 (36,180건)."""
    assert parse_yen("8,400万円") == 84_000_000
    assert parse_yen("1,100万円") == 11_000_000
    assert parse_yen("500万円") == 5_000_000
    assert parse_yen("110,000万円") == 1_100_000_000


def test_area_is_parsed_from_the_square_metre_format() -> None:
    assert parse_area("45㎡") == 45.0
    assert parse_area("1,200㎡") == 1200.0


@pytest.mark.parametrize("text", ["8400", "8,400円", "8,400万", ""])
def test_an_unknown_price_format_is_loud(text: str) -> None:
    """포맷이 바뀌면 0 으로 접지 않고 던진다 — 조용히 접으면 지표가 통째로 어긋난다."""
    with pytest.raises(TransactionShapeError):
        parse_yen(text)


@pytest.mark.parametrize("text", ["45", "45m2", ""])
def test_an_unknown_area_format_is_loud(text: str) -> None:
    with pytest.raises(TransactionShapeError):
        parse_area(text)


# --- 레코드 파싱 ---


def test_a_condo_becomes_a_unit_price() -> None:
    """총액이 아니라 ㎡당 단가다. 총액은 매물 크기에 좌우된다."""
    transaction = parse_transaction(_feature(price="3,200万円", area="20㎡"))
    assert transaction is not None
    assert transaction.unit_price_yen == pytest.approx(1_600_000.0)


def test_land_transactions_are_excluded() -> None:
    """토지가 섞인 종별은 ㎡당 단가의 뜻이 달라 한 분포에 넣을 수 없다."""
    assert parse_transaction(_feature(land_type="宅地(土地と建物)")) is None
    assert parse_transaction(_feature(land_type="宅地(土地)")) is None


def test_the_quarter_is_kept_so_staleness_is_visible() -> None:
    transaction = parse_transaction(_feature(quarter="2026年第1四半期"))
    assert transaction is not None
    assert transaction.quarter == "2026年第1四半期"


def test_a_response_missing_the_transaction_fields_is_rejected() -> None:
    """XPT001 은 `_index` 를 주지 않아 클라이언트가 정체를 대조할 수 없다.

    엔드포인트 번호가 바뀌어 다른 데이터셋이 와도 200 이므로 형태로 막는다.
    """
    other_dataset = {
        "geometry": {"type": "Point", "coordinates": [139.7, 35.7]},
        "properties": {"_id": "a", "_index": "bs006_preschool_2024"},
    }
    with pytest.raises(TransactionShapeError, match="land_type_name_ja"):
        parse_transaction(other_dataset)


def test_a_zero_area_is_rejected_rather_than_dividing() -> None:
    with pytest.raises(TransactionShapeError):
        parse_transaction(_feature(area="0㎡"))


def test_parse_all_keeps_only_condos() -> None:
    features = [
        _feature(),
        _feature(land_type="宅地(土地)"),
        _feature(),
    ]
    assert len(parse_all(features)) == 2


# --- 집계 ---


def _at(distance_deg: float, price: float) -> Transaction:
    return Transaction(
        lat=SHINJUKU[0] + distance_deg,
        lon=SHINJUKU[1],
        unit_price_yen=price,
        quarter="2025年第3四半期",
    )


def test_the_median_uses_only_transactions_inside_the_radius() -> None:
    inside = [_at(0.0, 1_000_000.0) for _ in range(MIN_SAMPLES)]
    far = [_at(0.05, 9_000_000.0) for _ in range(MIN_SAMPLES)]  # 약 5.5km
    median = median_unit_price_near(*SHINJUKU, [*inside, *far])
    assert median == pytest.approx(1_000_000.0)


def test_the_median_not_the_mean_so_one_luxury_sale_cannot_move_it() -> None:
    """한 동네에 15㎡ 원룸과 100㎡ 패밀리 매물이 섞여 있다."""
    prices = [500_000.0, 600_000.0, 700_000.0, 800_000.0, 20_000_000.0]
    median = median_unit_price_near(
        *SHINJUKU, [_at(0.0, price) for price in prices]
    )
    assert median == pytest.approx(700_000.0)


def test_too_few_transactions_is_missing_not_a_number() -> None:
    """桜田門 은 거래 1건으로 6,666,667엔/㎡ 이 나와 백분위 최상단을 차지했다.

    관청가라 주거 거래가 거의 없다. 결측이 옳다.
    """
    few = [_at(0.0, 6_666_667.0) for _ in range(MIN_SAMPLES - 1)]
    assert median_unit_price_near(*SHINJUKU, few) is None


def test_exactly_the_minimum_sample_count_is_enough() -> None:
    just_enough = [_at(0.0, 1_000_000.0) for _ in range(MIN_SAMPLES)]
    assert median_unit_price_near(*SHINJUKU, just_enough) is not None


def test_a_station_with_no_transactions_is_missing() -> None:
    """공항·물류센터처럼 주거 거래가 없는 역이 실제로 10곳 있다."""
    assert median_unit_price_near(*SHINJUKU, []) is None


# --- 분기 창 ---


def test_the_quarter_window_counts_backwards() -> None:
    assert quarter_range(2026, 1, 4) == ("20252", "20261")
    assert quarter_range(2025, 4, 4) == ("20251", "20254")


def test_the_quarter_window_crosses_the_year_boundary() -> None:
    assert quarter_range(2026, 2, 5) == ("20252", "20262")


def test_a_single_quarter_window_is_the_same_quarter() -> None:
    assert quarter_range(2025, 3, 1) == ("20253", "20253")


@pytest.mark.parametrize("quarter", [0, 5])
def test_an_impossible_quarter_is_refused(quarter: int) -> None:
    with pytest.raises(ValueError):
        quarter_range(2026, quarter, 4)


def test_a_non_positive_window_is_refused() -> None:
    with pytest.raises(ValueError):
        quarter_range(2026, 1, 0)
