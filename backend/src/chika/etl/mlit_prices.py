"""지표 13(시세) — MLIT 부동산 거래가격에서 역세권 ㎡당 단가 중앙값.

HTTP 도, 파일 IO 도 없다. 배치가 받아온 feature 를 넣으면 지표가 나온다.

**총액이 아니라 ㎡당 단가를 쓴다.** 응답의 총액은 매물 크기에 좌우되므로
(신주쿠 실측: 45㎡ 8,400만엔 vs 15㎡ 1,100만엔) 총액 중앙값은 그 동네의
시세가 아니라 그 동네에 흔한 매물 크기를 재게 된다.

API 의 단가 필드(`u_transaction_price_unit_price_square_meter_ja`)는 대부분
비어 있다 — 도쿄 1년치 중고맨션 36,180건 중 채워진 것이 51건뿐이었다.
그래서 총액과 면적에서 직접 계산한다.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from chika.domain.service.geo import distance_meters
from chika.etl.mlit_datasets import CONDO_LAND_TYPE

#: 중앙값을 낼 최소 거래 건수.
#:
#: 실측(도쿄 1년치, 반경 800m)에서 이 문턱이 걸러내는 것은 桜田門 단 하나였다.
#: 거래 1건으로 계산한 6,666,667엔/㎡ 이 다른 어떤 역보다 2.6배 높게 나와
#: 백분위 최상단을 차지했다. 관청가라 주거 거래가 거의 없는 곳이다.
#:
#: 문턱을 20 으로 올리면 虎ノ門(11건)·霞ヶ関(12건)·田園調布(18건)처럼
#: 값 자체는 타당한 역까지 버린다. 田園調布 는 저층 주택지라 맨션 거래가
#: 원래 적다 — 표본이 적은 것이 곧 이상치인 것은 아니다.
MIN_SAMPLES = 5

#: 이 필드들이 전부 있어야 거래 레코드로 인정한다. XPT001 은 `_index` 를 주지
#: 않아 클라이언트가 데이터셋 정체를 대조할 수 없다. 엔드포인트 번호가 바뀌어
#: 다른 데이터가 와도 200 이므로, 형태 검증을 여기서 대신한다.
REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "land_type_name_ja",
        "u_transaction_price_total_ja",
        "u_area_ja",
        "point_in_time_name_ja",
    }
)


class TransactionShapeError(RuntimeError):
    """XPT001 응답이 거래 레코드 형태가 아니다."""


@dataclass(frozen=True)
class Transaction:
    """거래 1건. 좌표는 지번이 아니라 약 1km 메시의 대표점이다.

    도쿄 23구 1년치 36,180건이 고유 좌표 515개를 공유했다 — 町丁目 이름이
    102개인 타일에서 좌표는 23개뿐이었고, 麹町 와 四谷本塩町 가 같은 좌표를
    받았다. 개별 거래의 위치가 아니라 익명화된 격자점이다.

    따라서 이 지표의 실질 해상도는 약 1km 이며, 다른 지표(반경 800m 실측
    개수)보다 거칠다. 역세권 하나가 격자점 몇 개를 걸치므로 역 단위 중앙값은
    성립하지만, "이 역 앞 건물의 시세"로 읽어서는 안 된다.
    """

    lat: float
    lon: float
    #: ㎡당 단가(엔). 총액 / 전용면적.
    unit_price_yen: float
    #: "2025年第3四半期". 배치가 어느 분기가 실제로 왔는지 보고하는 데 쓴다.
    quarter: str


def parse_yen(text: str) -> int:
    """"8,400万円" -> 84000000. 실측에서 이 포맷 하나뿐이었다."""
    body = text.replace(",", "").removesuffix("万円")
    if body == text.replace(",", ""):
        raise TransactionShapeError(f"총액 포맷이 '万円' 이 아니다: {text!r}")
    return int(body) * 10_000


def parse_area(text: str) -> float:
    """"45㎡" -> 45.0."""
    body = text.replace(",", "").removesuffix("㎡")
    if body == text.replace(",", ""):
        raise TransactionShapeError(f"면적 포맷이 '㎡' 가 아니다: {text!r}")
    return float(body)


def parse_transaction(feature: Mapping[str, object]) -> Transaction | None:
    """feature 하나를 거래로. 중고 맨션이 아니면 None.

    형태가 어긋나면 조용히 건너뛰지 않고 던진다 — 파싱 실패를 결측으로 접으면
    엔드포인트가 바뀌어도 지표가 그냥 비어서 나온다.
    """
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise TransactionShapeError("properties 가 dict 가 아니다")
    missing = REQUIRED_FIELDS - set(properties)
    if missing:
        raise TransactionShapeError(
            f"거래 레코드에 없는 필드: {sorted(missing)}. "
            "XPT001 이 다른 데이터셋을 돌려주고 있을 수 있다."
        )

    if properties["land_type_name_ja"] != CONDO_LAND_TYPE:
        return None

    area = parse_area(str(properties["u_area_ja"]))
    if area <= 0:
        raise TransactionShapeError(f"면적이 0 이하다: {properties['u_area_ja']!r}")

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise TransactionShapeError("geometry 가 dict 가 아니다")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise TransactionShapeError(f"좌표 형태가 아니다: {coordinates!r}")

    lon, lat = float(coordinates[0]), float(coordinates[1])
    return Transaction(
        lat=lat,
        lon=lon,
        unit_price_yen=parse_yen(str(properties["u_transaction_price_total_ja"])) / area,
        quarter=str(properties["point_in_time_name_ja"]),
    )


def parse_all(features: Iterable[Mapping[str, object]]) -> list[Transaction]:
    """중고 맨션 거래만 골라 파싱한다."""
    parsed = (parse_transaction(feature) for feature in features)
    return [transaction for transaction in parsed if transaction is not None]


def median_unit_price_near(
    lat: float,
    lon: float,
    transactions: Sequence[Transaction],
    radius_m: float = 800.0,
    min_samples: int = MIN_SAMPLES,
) -> float | None:
    """반경 안 거래의 ㎡당 단가 중앙값. 표본이 모자라면 None(결측).

    평균이 아니라 중앙값이다. 같은 동네에 15㎡ 원룸과 100㎡ 패밀리 매물이
    섞여 있고 고가 거래 하나가 평균을 끌어올린다.
    """
    near = [
        transaction.unit_price_yen
        for transaction in transactions
        if distance_meters(lat, lon, transaction.lat, transaction.lon) <= radius_m
    ]
    if len(near) < min_samples:
        return None
    return statistics.median(near)


def quarter_range(year: int, quarter: int, count: int) -> tuple[str, str]:
    """`(year, quarter)` 에서 거꾸로 `count` 분기의 `from`/`to` 파라미터.

    API 는 "20253" 같은 문자열을 받는다. 분기를 손으로 적으면 배치가 조용히
    옛 데이터를 계속 보게 되므로 호출 시점에서 계산한다.
    """
    if not 1 <= quarter <= 4:
        raise ValueError(f"분기는 1~4 다: {quarter}")
    if count < 1:
        raise ValueError(f"분기 수는 1 이상이다: {count}")
    index = year * 4 + (quarter - 1) - (count - 1)
    start_year, start_quarter = divmod(index, 4)
    return f"{start_year}{start_quarter + 1}", f"{year}{quarter}"
