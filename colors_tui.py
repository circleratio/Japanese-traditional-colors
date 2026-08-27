#!/usr/bin/env python3
"""Terminal UI for browsing Japanese traditional colors (日本の伝統色).

Pure standard library (curses + json + unicodedata), no third-party
dependencies. Run it with:

    python3 colors_tui.py

Keys:
    up/down, j/k   move selection
    left/right     switch color family filter
    /              search by name / reading / romaji
    Enter          show detail view for the selected color
    Esc / q        back / quit
"""
from __future__ import annotations

import curses
import json
import locale
import unicodedata
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).parent / "data" / "colors.json"

FAMILIES = ["all", "red", "orange", "yellow", "green", "blue", "purple", "brown", "neutral"]
FAMILY_LABELS = {
    "all": "すべて",
    "red": "赤系",
    "orange": "橙系",
    "yellow": "黄系",
    "green": "緑系",
    "blue": "青系",
    "purple": "紫系",
    "brown": "茶系",
    "neutral": "黒白灰系",
}


def load_colors() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def display_width(s: str) -> int:
    """Approximate terminal column width, counting full-width chars as 2."""
    width = 0
    for ch in s:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad_to_width(s: str, width: int) -> str:
    w = display_width(s)
    return s + " " * max(0, width - w)


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    h = hex_code.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# The 6x6x6 color cube + grayscale ramp used by the standard xterm-256 palette.
_CUBE_STEPS = (0, 95, 135, 175, 215, 255)


def _nearest_cube_index(value: int) -> int:
    return min(range(6), key=lambda i: abs(_CUBE_STEPS[i] - value))


def hex_to_xterm256(hex_code: str) -> int:
    """Map an arbitrary 24-bit color to the closest xterm-256 palette index."""
    r, g, b = hex_to_rgb(hex_code)

    ri, gi, bi = _nearest_cube_index(r), _nearest_cube_index(g), _nearest_cube_index(b)
    cube_color = (
        _CUBE_STEPS[ri],
        _CUBE_STEPS[gi],
        _CUBE_STEPS[bi],
    )
    cube_index = 16 + 36 * ri + 6 * gi + bi

    gray_avg = round((r + g + b) / 3)
    if gray_avg < 8:
        gray_index, gray_value = 16, 0
    elif gray_avg > 238:
        gray_index, gray_value = 231, 255
    else:
        step = round((gray_avg - 8) / 10)
        gray_index = 232 + step
        gray_value = 8 + step * 10

    def dist(c):
        return (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2

    if dist(cube_color) <= dist((gray_value,) * 3):
        return cube_index
    return gray_index


def init_color_pairs(colors: list[dict]) -> dict[str, int]:
    """Register one curses color pair per unique color, return hex -> pair id."""
    curses.start_color()
    curses.use_default_colors()
    pair_by_hex: dict[str, int] = {}
    pair_id = 1
    for c in colors:
        if c["hex"] in pair_by_hex:
            continue
        xterm_index = hex_to_xterm256(c["hex"]) if curses.COLORS >= 256 else hex_to_xterm256(c["hex"]) % 8
        try:
            curses.init_pair(pair_id, curses.COLOR_BLACK, xterm_index)
        except curses.error:
            continue
        pair_by_hex[c["hex"]] = pair_id
        pair_id += 1
        if pair_id >= curses.COLOR_PAIRS:
            break
    return pair_by_hex


def matches_query(color: dict, query: str) -> bool:
    if not query:
        return True
    q = query.lower()
    return q in color["name"].lower() or q in color["reading"].lower() or q in color["romaji"].lower()


def filtered_colors(colors: list[dict], family: str, query: str) -> list[dict]:
    result = colors
    if family != "all":
        result = [c for c in result if c["family"] == family]
    if query:
        result = [c for c in result if matches_query(c, query)]
    return result


def draw_header(stdscr, width: int, family: str, query: str, count: int, total: int) -> None:
    title = "日本の伝統色 TUI"
    stdscr.addstr(0, 0, pad_to_width(title, width), curses.A_BOLD)
    family_label = f"分類: {FAMILY_LABELS[family]} (←/→で切替)"
    query_label = f"  検索: {query}" if query else "  検索: (/ で入力)"
    stdscr.addstr(1, 0, pad_to_width(family_label + query_label, width))
    stdscr.addstr(2, 0, pad_to_width(f"{count} / {total} 件", width))
    stdscr.addstr(3, 0, "-" * min(width, 200))


def draw_footer(stdscr, height: int, width: int, message: str = "") -> None:
    help_text = message or "↑/↓:選択  ←/→:分類  /:検索  Enter:詳細  q:終了"
    stdscr.addstr(height - 1, 0, pad_to_width(help_text, width - 1), curses.A_REVERSE)


def draw_list(stdscr, colors: list[dict], selected: int, top: int, list_height: int, width: int,
              pair_by_hex: dict[str, int]) -> None:
    swatch_width = 4
    for row in range(list_height):
        idx = top + row
        y = 4 + row
        if idx >= len(colors):
            stdscr.addstr(y, 0, pad_to_width("", width))
            continue
        c = colors[idx]
        pair = pair_by_hex.get(c["hex"])
        attr = curses.color_pair(pair) if pair else curses.A_NORMAL
        line_attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL

        stdscr.addstr(y, 0, " " * swatch_width, attr)
        label = f" {c['name']} ({c['reading']})"
        label = pad_to_width(label, 28)
        hex_label = pad_to_width(c["hex"], 9)
        line = f"{label}{hex_label}"
        remaining = max(0, width - swatch_width - display_width(line) - 1)
        stdscr.addstr(y, swatch_width, (" " + line + " " * remaining)[: width - swatch_width], line_attr)


def draw_detail(stdscr, color: dict, width: int, pair_by_hex: dict[str, int]) -> None:
    pair = pair_by_hex.get(color["hex"])
    attr = curses.color_pair(pair) if pair else curses.A_NORMAL
    stdscr.addstr(4, 0, " " * min(width, 12), attr)
    r, g, b = hex_to_rgb(color["hex"])
    lines = [
        f"名前: {color['name']} ({color['reading']} / {color['romaji']})",
        f"分類: {FAMILY_LABELS.get(color['family'], color['family'])}",
        f"HEX : {color['hex']}",
        f"RGB : {r}, {g}, {b}",
        "",
        f"説明: {color['note']}",
    ]
    for i, line in enumerate(lines):
        stdscr.addstr(6 + i, 0, pad_to_width(line, width))


def prompt(stdscr, height: int, width: int, label: str) -> str:
    curses.echo()
    curses.curs_set(1)
    stdscr.addstr(height - 1, 0, pad_to_width(label, width - 1), curses.A_REVERSE)
    stdscr.move(height - 1, display_width(label))
    stdscr.refresh()
    try:
        raw = stdscr.getstr(height - 1, display_width(label), width - display_width(label) - 1)
        text = raw.decode("utf-8", errors="ignore")
    except curses.error:
        text = ""
    curses.noecho()
    curses.curs_set(0)
    return text


def run(stdscr) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    colors = load_colors()
    pair_by_hex = init_color_pairs(colors)

    family_idx = 0
    query = ""
    selected = 0
    top = 0
    view = "list"  # "list" or "detail"
    message = ""

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        family = FAMILIES[family_idx]
        visible = filtered_colors(colors, family, query)
        if not visible:
            selected = 0
        else:
            selected = max(0, min(selected, len(visible) - 1))

        list_height = max(1, height - 5)
        if selected < top:
            top = selected
        elif selected >= top + list_height:
            top = selected - list_height + 1

        draw_header(stdscr, width, family, query, len(visible), len(colors))

        if view == "detail" and visible:
            draw_detail(stdscr, visible[selected], width, pair_by_hex)
            draw_footer(stdscr, height, width, "Esc/q: 一覧へ戻る")
        else:
            if visible:
                draw_list(stdscr, visible, selected, top, list_height, width, pair_by_hex)
            else:
                stdscr.addstr(4, 0, "該当する色がありません。")
            draw_footer(stdscr, height, width, message)
            message = ""

        stdscr.refresh()
        key = stdscr.getch()

        if view == "detail":
            if key in (27, ord("q"), curses.KEY_BACKSPACE):
                view = "list"
            continue

        if key in (ord("q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = min(len(visible) - 1, selected + 1) if visible else 0
        elif key == curses.KEY_LEFT:
            family_idx = (family_idx - 1) % len(FAMILIES)
            selected = 0
        elif key == curses.KEY_RIGHT:
            family_idx = (family_idx + 1) % len(FAMILIES)
            selected = 0
        elif key in (curses.KEY_ENTER, 10, 13):
            if visible:
                view = "detail"
        elif key == ord("/"):
            query = prompt(stdscr, height, width, "検索 (名前/よみ/ローマ字): ")
            selected = 0


def main() -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(run)


if __name__ == "__main__":
    main()
