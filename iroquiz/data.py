"""日本の伝統色 36色分のデータ読み込み。

各色の名前・読み・16進カラーコード・特徴・トリビアは、日本の伝統色に関する
一般的な資料・文献で広く知られている内容を基にまとめたもの。カラーコードは
染料・顔料の色味を表す目安の近似値であり、厳密な測色値ではない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "data" / "colors.json"


@dataclass(frozen=True)
class Color:
    name: str
    yomi: str
    hex: str
    category: str
    description: str
    trivia: str


CATEGORY_LABEL = {
    "red": "赤系",
    "orange": "橙系",
    "yellow": "黄系",
    "green": "緑系",
    "blue": "青系",
    "purple": "紫系",
    "neutral": "白・黒・鼠系",
}

CATEGORY_ORDER = tuple(CATEGORY_LABEL.keys())


@lru_cache(maxsize=1)
def load_colors() -> tuple[Color, ...]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return tuple(Color(**entry) for entry in raw)
