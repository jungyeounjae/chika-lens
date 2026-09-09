"""지표 14(재해위험) 후보 엔드포인트 4개의 정체·스키마 확인 프로브.

XKT025/027/029 는 §6.2.6 에서 `_index` 로 이미 확인했지만, XKT026(홍수)은
번호만 문서에서 봤을 뿐 실측으로 정체를 대조한 적이 없다 — 다른 엔드포인트들이
"번호를 추측으로 붙였다가 절반이 틀렸다"는 전례가 있으므로 그대로 믿지 않는다.

`index_prefix=None` 인 임시 MlitDataset 으로 호출해 클라이언트의 정체 검증을
건너뛰고, 대신 이 스크립트가 `_index`·속성 스키마를 직접 찍어서 사람이 확인한다.

저지대·매립지 역 근처를 골랐다 — 액상화·침수·해일이 실제로 있을 가능성이
높은 곳이라야 빈 응답과 "정상인데 0건"을 구분할 수 있다. 토사재해는 23구
평지에는 거의 없어 0건이 나올 수 있다 — 그 자체가 정보다.

사용법:

    source scripts/load-env.sh
    uv run --extra etl python scripts/probe_hazards.py
"""

from __future__ import annotations

import collections
import json
import os
import sys

from chika.etl.mlit_client import MlitClient, tile_xy
from chika.etl.mlit_datasets import MlitDataset

#: 저지대·매립지 역. 4개 하자드가 겹칠 가능성이 높은 후보들.
PROBE_POINTS: dict[str, tuple[float, float]] = {
    "西葛西": (35.664583, 139.859355),
    "新木場": (35.64578, 139.826605),
    "台場": (35.62587, 139.771375),
    "東雲": (35.64082, 139.80416),
}

#: 문서상 번호. `_index` 가 다르면 이 번호는 폐기 대상이다.
CANDIDATES: dict[str, int] = {
    "XKT025": 13,  # 액상화 경향 (문서상 z=13)
    "XKT026": 15,  # 홍수 침수 상정 최대규모 (문서상 z=15 만) — 정체 미확인
    "XKT027": 13,  # 해일 침수상정
    "XKT029": 13,  # 토사재해 경계구역
}


def _api_key() -> str:
    key = os.environ.get("MLIT_API_KEY", "").strip()
    if not key:
        sys.exit("MLIT_API_KEY 가 비어 있다. source scripts/load-env.sh 를 먼저 돌린다.")
    return key


def main() -> None:
    client = MlitClient(_api_key())
    # index_prefix=None -> 클라이언트가 정체 검증을 건너뛴다. 그게 이 스크립트의 일이다.
    probe_datasets = {
        endpoint: MlitDataset(endpoint, endpoint, None, zoom=zoom)
        for endpoint, zoom in CANDIDATES.items()
    }

    for endpoint, dataset in probe_datasets.items():
        print(f"\n{'=' * 60}\n{endpoint} (z={dataset.zoom})\n{'=' * 60}")
        all_features: list[dict[str, object]] = []
        for name, (lat, lon) in PROBE_POINTS.items():
            x, y = tile_xy(lat, lon, dataset.zoom)
            try:
                features = client.features(dataset, x, y)
            except Exception as exc:  # noqa: BLE001 — 프로브는 낙관적으로 계속한다
                print(f"  {name}: 오류 {exc}")
                continue
            print(f"  {name} (tile {x},{y}): {len(features)}건")
            all_features.extend(features)

        if not all_features:
            print("  -> 4개 저지대 역 전부 0건. 줌·좌표·엔드포인트 번호를 의심한다.")
            continue

        indexes = collections.Counter(
            f.get("properties", {}).get("_index", "(없음)")  # type: ignore[union-attr]
            for f in all_features
        )
        print(f"  _index 분포: {dict(indexes)}")

        sample = all_features[0]
        geometry = sample.get("geometry", {})
        properties = sample.get("properties", {})
        print(f"  geometry.type: {geometry.get('type')}")  # type: ignore[union-attr]
        print(f"  properties 키: {sorted(properties.keys())}")  # type: ignore[union-attr]
        print(f"  샘플 properties:\n{json.dumps(properties, ensure_ascii=False, indent=4)}")

    print(f"\n{'=' * 60}\n호출 {client.calls_made}건 사용 (과금 없음)\n{'=' * 60}")


if __name__ == "__main__":
    main()
