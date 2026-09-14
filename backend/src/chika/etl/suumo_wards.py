"""도쿄 23구 이름 <-> SUUMO 신축 페이지 URL 슬러그.

https://suumo.jp/ms/shinchiku/tokyo/ 의 구별 링크(`/ms/shinchiku/tokyo/sc_<slug>/`)를
실측해서 고정한 상수다(2026-09-14). SUUMO 가 슬러그를 바꾸는 일은 거의 없지만,
바뀌면 build_new_construction.py 가 그 구만 0건으로 보고하므로 알아챌 수 있다.
"""

from __future__ import annotations

TOKYO_23_WARDS: dict[str, str] = {
    "千代田区": "chiyoda",
    "中央区": "chuo",
    "港区": "minato",
    "新宿区": "shinjuku",
    "文京区": "bunkyo",
    "台東区": "taito",
    "墨田区": "sumida",
    "江東区": "koto",
    "品川区": "shinagawa",
    "目黒区": "meguro",
    "大田区": "ota",
    "世田谷区": "setagaya",
    "渋谷区": "shibuya",
    "中野区": "nakano",
    "杉並区": "suginami",
    "豊島区": "toshima",
    "北区": "kita",
    "荒川区": "arakawa",
    "板橋区": "itabashi",
    "練馬区": "nerima",
    "足立区": "adachi",
    "葛飾区": "katsushika",
    "江戸川区": "edogawa",
}
