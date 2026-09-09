"""지표 14(재해위험) 파싱과 집계. 4개 MLIT 하자드 레이어를 raw value 하나로 합친다.

각 레이어의 등급 필드 방향은 실측만으로는 못 정한다 — 프로브(2026-09-09)로
값 도메인은 봤지만, 그 숫자가 뭘 뜻하는지는 공식 명세서로 확정했다:

- **액상화**(`liquefaction_tendency_level`): **작을수록 위험**, 1~5의 5단계다
  (1=非常に液状化しやすい ~ 5=液状化しにくい). `note` 필드로 뜻을 확인했다.
  `6`은 등급이 아니라 "評価対象外"(河道 등) — 신호로 안 쓴다.

  저지대 4곳(西葛西·新木場·台場·東雲)만 본 첫 프로브에서는 1~3, 6만 보여
  3단계로 오판할 뻔했다 — 그 지역 자체가 전부 고위험지라 4·5(낮은 위험)가
  안 잡혔을 뿐이었다. 489역 전체를 돌리고 나서야 5까지 나왔다. 표본이 좁으면
  등급 개수 자체를 놓칠 수 있다는 사례다.
- **홍수**(`A31a_205`): **클수록 위험**. 국가 표준 想定最大規模 6단계
  (1: 0.5m미만 ~ 6: 20m이상). 방향이 액상화와 반대다.
- **해일**(`A49_003`): 침수심 구간 문자열. 알려진 구간만 허용한다 — 새 구간이
  오면 등급표를 갱신해야 한다는 뜻이므로 조용히 넘기지 않는다.
- **토사재해**(`A33_002`, 区域区分): 4개 코드지만 위험 **축은 2개**다.
  1=Yellow(지정완료), 2=Red(지정완료), 3=Yellow(지정 전/조사단계),
  4=Red(지정 전/조사단계). 1/3 과 2/4 는 지정 절차 단계 차이일 뿐 위험
  정도는 같아, Red(2,4) > Yellow(1,3) 둘로 묶는다. 처음엔 1=Yellow, 2=Red
  뿐이라고 알고 있었는데 489역 전체에서 3·4가 나와 공식 코드표로 다시
  확인했다. `A33_001`(급경사지/토석류/땅밀림)은 위험 **종류**라 점수에
  안 쓴다 — 도쿄 23구 안에서는 지형상 급경사지(1)만 나타났다.

레이어마다 등급 개수·방향이 달라 원시값을 그대로 비교할 수 없다. 그래서
전부 0~1로 정규화한 뒤에만 비교한다 — "3"이 액상화에서는 약간 위험, 홍수
6단계 체계에서는 절반 위험을 뜻해서는 안 된다.

거리 감쇠는 분기 없이 하나의 식으로 "내부"와 "근접"을 함께 표현한다
(`decayed_severity`). 폴리곤 안이면 거리 0이라 등급이 그대로 나오고, 밖이면
거리에 비례해 깎이다가 `DECAY_M` 밖에서 0이 된다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from chika.domain.service.geo import distance_meters

#: 폴리곤 밖에서 위험이 완전히 사라지는 거리. 상담 제안값 — 실측 근거는 없는
#: 튜닝 가능한 값이다.
# ponytail: 경험적 근거 없는 고정값. 근접 사례가 쌓이면 다시 본다.
DECAY_M = 500.0


class HazardShapeError(ValueError):
    """알려진 등급 값이 아니다. 조용히 무시하면 위험도가 소리 없이 틀어진다."""


# --- 레이어별 등급 -> 0~1 심각도 (공식 명세서 확인, 2026-09-09) ---

#: 액상화. 1~5의 5단계, 작을수록 위험이라 정규화 순서를 뒤집는다.
#: 6(평가 대상 외)은 매핑에 없어 별도로 걸러낸다.
_LIQUEFACTION_MAX_LEVEL = 5
_LIQUEFACTION_SEVERITY: dict[int, float] = {
    level: (_LIQUEFACTION_MAX_LEVEL - level + 1) / _LIQUEFACTION_MAX_LEVEL
    for level in range(1, _LIQUEFACTION_MAX_LEVEL + 1)
}
_LIQUEFACTION_EXCLUDED = frozenset({6})

#: 홍수. 想定最大規模 6단계, 클수록 위험.
_FLOOD_MAX_LEVEL = 6

#: 해일 침수심 구간. 얕은 것부터 순서대로 — 인덱스가 곧 등급 순위다.
#:
#: "10m以上"은 확인 없이 지어낸 값이었다 — 4곳짜리 프로브에서 "5m以上10m未満"이
#: 최고였길래 그 위 구간을 열린 구간으로 짐작했다. 489역 전체를 돌리자 실제
#: 값은 "10m以上20m未満"이었다. 짐작이 우연히 순서상 맞아떨어졌을 뿐 존재하지
#: 않는 문자열이었다 — `storm_surge_severity`가 이 문자열과 매치해 통과됐다면
#: 조용한 오답으로 남았을 것이다.
_STORM_SURGE_BANDS: tuple[str, ...] = (
    "0.3m未満",
    "0.3m以上0.5m未満",
    "0.5m以上1m未満",
    "1m以上3m未満",
    "3m以上5m未満",
    "5m以上10m未満",
    "10m以上20m未満",
)

#: 토사재해 区域区分. 4개 코드가 위험 2단계(Yellow/Red) × 지정 단계(완료/조사중)로
#: 갈린다. 지정 단계는 절차 문제라 위험도에 안 넣는다 — 1·3을 Yellow로,
#: 2·4를 Red로 같은 값에 묶는다.
_SEDIMENT_SEVERITY: dict[int, float] = {1: 0.6, 2: 1.0, 3: 0.6, 4: 1.0}


def liquefaction_severity(level: int) -> float | None:
    """`None` 은 이 폴리곤을 위험 신호로 쓰지 않는다는 뜻이다 (평가 대상 외)."""
    if level in _LIQUEFACTION_EXCLUDED:
        return None
    try:
        return _LIQUEFACTION_SEVERITY[level]
    except KeyError:
        raise HazardShapeError(f"liquefaction_tendency_level: {level!r}") from None


def flood_severity(level: int) -> float:
    if not 1 <= level <= _FLOOD_MAX_LEVEL:
        raise HazardShapeError(f"A31a_205: {level!r}")
    return level / _FLOOD_MAX_LEVEL


def storm_surge_severity(band: str) -> float:
    try:
        rank = _STORM_SURGE_BANDS.index(band)
    except ValueError:
        raise HazardShapeError(f"A49_003: {band!r}") from None
    return rank / (len(_STORM_SURGE_BANDS) - 1)


def sediment_severity(degree_code: int) -> float:
    try:
        return _SEDIMENT_SEVERITY[degree_code]
    except KeyError:
        raise HazardShapeError(f"A33_002: {degree_code!r}") from None


@dataclass(frozen=True)
class HazardZone:
    geometry: BaseGeometry
    severity: float


def _property(feature: dict[str, object], key: str) -> object:
    properties = feature.get("properties")
    if not isinstance(properties, dict) or key not in properties:
        raise HazardShapeError(f"{key} 없음: {feature!r}")
    return properties[key]


#: 레이어별 등급 필드 이름과 심각도 함수. `parse_all` 이 이 표만 보고 분기한다.
_LAYER_PARSERS: dict[str, tuple[str, object]] = {
    "liquefaction": ("liquefaction_tendency_level", liquefaction_severity),
    "flood": ("A31a_205", flood_severity),
    "storm_surge": ("A49_003", storm_surge_severity),
    "sediment": ("A33_002", sediment_severity),
}


def parse_hazard(feature: dict[str, object], layer: str) -> HazardZone | None:
    """feature 하나를 심각도 붙은 폴리곤으로. 신호로 안 쓰는 값이면 `None`."""
    field, severity_fn = _LAYER_PARSERS[layer]
    severity = severity_fn(_property(feature, field))  # type: ignore[operator]
    if severity is None:
        return None
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise HazardShapeError(f"geometry 없음: {feature!r}")
    return HazardZone(geometry=shape(geometry), severity=severity)


def parse_all(features: Sequence[dict[str, object]], layer: str) -> list[HazardZone]:
    zones = (parse_hazard(f, layer) for f in features)
    return [z for z in zones if z is not None]


def decayed_severity(severity: float, distance_m: float) -> float:
    """내부(거리 0)와 근접(거리 > 0)을 같은 식으로 다룬다 — 분기가 없다."""
    return severity * max(0.0, 1.0 - distance_m / DECAY_M)


def _nearest_distance_m(lat: float, lon: float, geometry: BaseGeometry) -> float:
    point = Point(lon, lat)
    if geometry.distance(point) == 0:
        return 0.0
    nearest_on_geometry, _ = nearest_points(geometry, point)
    return distance_meters(lat, lon, nearest_on_geometry.y, nearest_on_geometry.x)


class HazardIndex:
    """4개 레이어를 합친 폴리곤 집합. 역마다 최댓값 위험도를 빠르게 찾는다.

    레이어별로 최댓값을 낸 뒤 4개를 다시 최댓값 하는 것과, 전 폴리곤을 합쳐
    한 번에 최댓값 하는 것은 같은 결과다(최댓값의 최댓값 = 합집합의 최댓값).
    그래서 레이어를 구분해서 들고 다닐 필요가 없다 — 하나의 트리로 충분하다.
    """

    def __init__(self, zones: Sequence[HazardZone]) -> None:
        self._zones = list(zones)
        self._tree = STRtree([z.geometry for z in self._zones])

    def risk_near(self, lat: float, lon: float) -> float:
        """반경 `DECAY_M` 안에 걸리는 게 없으면 0.0(위험 없음)이다 — 결측이 아니다."""
        point = Point(lon, lat)
        search = point.buffer(DECAY_M / 111_320.0)  # 대략 미터->도, 근접 검색용 여유
        candidates = self._tree.query(search)
        best = 0.0
        for index in candidates:
            zone = self._zones[index]
            distance = _nearest_distance_m(lat, lon, zone.geometry)
            best = max(best, decayed_severity(zone.severity, distance))
        return best
