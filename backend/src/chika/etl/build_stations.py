"""역 마스터 생성 CLI.

사전 준비 (수동):
  1. https://nlftp.mlit.go.jp/ksj/ 에서 N02(鉄道) 최신 연도판 GeoJSON을 받는다.
  2. 같은 사이트에서 N03(行政区域) 東京都 GeoJSON을 받는다.
  3. 두 파일 경로를 아래 인자로 넘긴다.

  uv run python -m chika.etl.build_stations \\
      --n02 ~/Downloads/N02.geojson \\
      --n03 ~/Downloads/N03-tokyo.geojson \\
      --out data/stations.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from chika.etl.station_master import parse_stations, parse_ward_polygons

#: 도쿄 23구. N03에는 시·정·촌도 섞여 있으므로 여기서 걸러낸다.
TOKYO_23_WARDS: frozenset[str] = frozenset(
    {
        "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区",
        "墨田区", "江東区", "品川区", "目黒区", "大田区", "世田谷区",
        "渋谷区", "中野区", "杉並区", "豊島区", "北区", "荒川区",
        "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区",
    }
)


def main() -> None:
    parser = argparse.ArgumentParser(description="국토수치정보에서 역 마스터를 만든다")
    parser.add_argument("--n02", type=Path, required=True, help="N02 철도 GeoJSON")
    parser.add_argument("--n03", type=Path, required=True, help="N03 행정구역 GeoJSON")
    parser.add_argument("--out", type=Path, default=Path("data/stations.json"))
    args = parser.parse_args()

    n02 = json.loads(args.n02.read_text(encoding="utf-8"))
    n03 = json.loads(args.n03.read_text(encoding="utf-8"))

    wards = [(name, ring) for name, ring in parse_ward_polygons(n03) if name in TOKYO_23_WARDS]
    stations = parse_stations(n02, wards)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([dataclasses.asdict(s) for s in stations], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(stations)} stations -> {args.out}")


if __name__ == "__main__":
    main()
