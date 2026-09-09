"""지표 20(유동인구) 파싱과 집계 — MLIT XKT015(駅別乗降客数, 국토수치정보 S12).

공식 규격 확인(2026-09-09, 사용자 제공):

- Geometry 는 역 지점이 아니라 **노선 구간 LineString** 이다 — 역의 대표
  좌표가 필요하면 구간의 대표점(여기서는 좌표 평균)을 쓴다.
- **환승 거점역은 300m 이내 동일 역을 그룹 코드(`S12_001g`)로 묶는다.**
  그룹 안에서 사업자·노선별로 레코드가 여러 개 나오는데, 중복 합산을
  막으려고 "대표 레코드"에만 실측값을 주고 나머지는 0으로 채운다.
  `新宿`(그룹 003700)을 실측(2026-09-09)해 보면 JR 中央線·小田急・京王・
  東京地下鉄丸ノ内線 은 대표(값 있음)인데, 같은 그룹의 JR 山手線·都営
  大江戸線・都営新宿線 은 중복(값 0)이었다 — **사업자당 하나가 아니라
  대표로 뽑힌 노선만** 값을 가진다.
- 대표 레코드 판별 필드는 연도마다 4칸 반복 구조([대표코드, 유무코드,
  비고, 값])의 첫 칸이다. 연도 Y 의 값 필드 번호는 `9 + (Y-2011)*4`,
  대표코드 필드는 그 3칸 앞이다. 예: 2023년 값=`S12_057`, 대표코드=`S12_054`.
- **집계는 MAX 가 아니라 SUM 이다.** 신주쿠처럼 사업자가 여럿인 역은
  대표 레코드도 사업자 수만큼 여럿이다 — MAX 를 쓰면 가장 큰 사업자
  하나만 남아 다사업자 환승역을 실제보다 훨씬 적게 계산하게 된다.
  실측: 이 방식으로 신주쿠(그룹 003700, 프로브 타일 기준 4개 사업자
  대표 레코드 합) 약 298만 명/일 — 세계 최고 환승역 규모와 정합적이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: 프로브(2026-09-09) 시점 최신 연도. MLIT 가 갱신하면 이 값만 올리면 된다 —
#: 필드 번호는 공식 규격의 고정 산식으로 유도한다.
LATEST_YEAR = 2023

_BASE_YEAR = 2011
_BASE_VALUE_FIELD = 9

#: 대표 레코드 코드. "1"=대표(실측값 있음), 그 외(관측 "2")=중복(0으로 채움).
_REPRESENTATIVE_CODE = "1"


class RidershipShapeError(ValueError):
    """알려진 필드 구조가 아니다. 조용히 넘기면 유동인구가 소리 없이 틀어진다."""


def _value_field(year: int) -> str:
    return f"S12_{_BASE_VALUE_FIELD + (year - _BASE_YEAR) * 4:03d}"


def _representative_field(year: int) -> str:
    value_num = _BASE_VALUE_FIELD + (year - _BASE_YEAR) * 4
    return f"S12_{value_num - 3:03d}"


@dataclass(frozen=True)
class RidershipPoint:
    group_code: str
    station_name: str
    lat: float
    lon: float
    value: float
    is_representative: bool


def _centroid(geometry: dict[str, object]) -> tuple[float, float]:
    """LineString 좌표 평균을 대표점으로 쓴다. 별도 폴리곤 연산이 필요 없다."""
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise RidershipShapeError(f"좌표 없는 geometry: {geometry!r}")
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def parse_ridership(feature: dict[str, object], year: int = LATEST_YEAR) -> RidershipPoint:
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise RidershipShapeError(f"properties 없음: {feature!r}")

    def _get(key: str) -> object:
        if key not in properties:
            raise RidershipShapeError(f"{key} 없음: {feature!r}")
        return properties[key]

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise RidershipShapeError(f"geometry 없음: {feature!r}")
    lat, lon = _centroid(geometry)

    value_raw = _get(_value_field(year))
    representative_raw = _get(_representative_field(year))
    try:
        value = float(value_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise RidershipShapeError(f"{_value_field(year)}: {value_raw!r}") from exc

    return RidershipPoint(
        group_code=str(_get("S12_001g")),
        station_name=str(_get("S12_001_ja")),
        lat=lat,
        lon=lon,
        value=value,
        is_representative=str(representative_raw) == _REPRESENTATIVE_CODE,
    )


def parse_all(
    features: Sequence[dict[str, object]], year: int = LATEST_YEAR
) -> list[RidershipPoint]:
    return [parse_ridership(f, year) for f in features]


@dataclass(frozen=True)
class RidershipGroup:
    group_code: str
    station_name: str
    lat: float
    lon: float
    total: float


def aggregate_by_group(points: Sequence[RidershipPoint]) -> list[RidershipGroup]:
    """대표 레코드만 골라 그룹 코드(300m 통합역)별로 **합산**한다.

    대표점 좌표는 그 그룹에 속한 대표 레코드 전부의 **평균**을 쓴다. 첫
    레코드 하나만 썼다가 品川역에서 재현됐다 — 東海道新幹線 플랫폼
    레코드가 山手線 플랫폼보다 역 좌표에서 313m 떨어져 있어(신칸센 홈이
    재래선과 물리적으로 분리돼 있다), 그게 먼저 나오면 매칭 반경(300m)
    밖으로 밀려 品川 전체가 결측 처리됐다. 평균을 쓰면 어느 레코드가
    먼저 나오든 대표점이 실제 역 중심에 가깝게 안정된다.
    """
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    coords: dict[str, list[tuple[float, float]]] = {}
    for point in points:
        if not point.is_representative:
            continue
        totals[point.group_code] = totals.get(point.group_code, 0.0) + point.value
        names.setdefault(point.group_code, point.station_name)
        coords.setdefault(point.group_code, []).append((point.lat, point.lon))

    return [
        RidershipGroup(
            group_code=code,
            station_name=names[code],
            lat=sum(lat for lat, _ in coords[code]) / len(coords[code]),
            lon=sum(lon for _, lon in coords[code]) / len(coords[code]),
            total=total,
        )
        for code, total in totals.items()
    ]
