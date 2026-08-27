"""curses ベースの TUI 画面。"""

from __future__ import annotations

import curses
import locale
import random
import unicodedata

from iroquiz.data import CATEGORY_LABEL, CATEGORY_ORDER, Color, load_colors
from iroquiz.quiz import KIND_LABEL, QUESTION_KINDS, grade, make_question
from iroquiz.stats import DEFAULT_STATS_PATH, Stats

_SKIP = "skip"
_QUIT = "quit"

_BASE_RGB = {
    curses.COLOR_BLACK: (0, 0, 0),
    curses.COLOR_RED: (128, 0, 0),
    curses.COLOR_GREEN: (0, 128, 0),
    curses.COLOR_YELLOW: (128, 128, 0),
    curses.COLOR_BLUE: (0, 0, 128),
    curses.COLOR_MAGENTA: (128, 0, 128),
    curses.COLOR_CYAN: (0, 128, 128),
    curses.COLOR_WHITE: (192, 192, 192),
}


def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(text: str) -> int:
    return sum(_char_width(c) for c in text)


def _truncate_to_width(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    out = []
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > max_width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def _wrap_to_width(text: str, max_width: int) -> list[str]:
    """表示カラム数基準で、日本語を含むテキストを複数行に折り返す。"""
    if max_width <= 0:
        return [text]
    lines: list[str] = []
    current = ""
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > max_width and current:
            lines.append(current)
            current = ""
            used = 0
        current += ch
        used += w
    if current:
        lines.append(current)
    return lines or [""]


def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    try:
        win.addstr(y, x, _truncate_to_width(text, max_x - x - 1), attr)
    except curses.error:
        pass


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    h = hex_code.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _nearest_base_color(hex_code: str) -> int:
    r, g, b = _hex_to_rgb(hex_code)
    best_const = curses.COLOR_WHITE
    best_dist = None
    for const, (br, bg, bb) in _BASE_RGB.items():
        dist = (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_const = const
    return best_const


def _swatch_pair(hex_code: str) -> int:
    return 3 + _nearest_base_color(hex_code)


def _draw_swatch(win, y: int, x: int, width: int, height: int, hex_code: str) -> None:
    pair = curses.color_pair(_swatch_pair(hex_code))
    for row in range(height):
        _safe_addstr(win, y + row, x, " " * width, pair)


def _wait_key(stdscr) -> int:
    return stdscr.getch()


def main_menu(stdscr, colors: tuple[Color, ...], stats: Stats) -> None:
    items = [
        ("1", "色名当てクイズ(全色)", lambda: practice_screen(stdscr, colors, stats, "name")),
        ("2", "特徴当てクイズ(全色)", lambda: practice_screen(stdscr, colors, stats, "description")),
        ("3", "トリビア当てクイズ(全色)", lambda: practice_screen(stdscr, colors, stats, "trivia")),
        ("4", "カテゴリを指定して出題", lambda: category_filter_menu(stdscr, colors, stats)),
        ("5", "苦手な色を優先して出題", lambda: practice_screen(stdscr, colors, stats, None, weak_only=True)),
        ("6", "一覧表示(カテゴリ順)", lambda: browse_screen(stdscr, colors)),
        ("7", "成績を見る", lambda: stats_screen(stdscr, colors, stats)),
        ("8", "成績をリセット", lambda: reset_stats_screen(stdscr, stats)),
        ("q", "終了", None),
    ]
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = "日本の伝統色クイズ"
        _safe_addstr(stdscr, 1, max(0, (w - _display_width(title)) // 2), title, curses.A_BOLD)
        correct, wrong = stats.totals()
        total = correct + wrong
        acc = f"{correct}/{total} 正解 ({correct / total * 100:.1f}%)" if total else "まだ記録がありません"
        _safe_addstr(stdscr, 3, 4, f"これまでの成績: {acc}")

        for i, (key, label, _) in enumerate(items):
            _safe_addstr(stdscr, 6 + i, 6, f"[{key}] {label}")

        _safe_addstr(stdscr, 7 + len(items), 4, "キーを押して選択してください。", curses.A_DIM)
        stdscr.refresh()

        ch = _wait_key(stdscr)
        try:
            key_char = chr(ch) if 0 <= ch < 256 else ""
        except ValueError:
            key_char = ""

        if key_char == "q" or ch == 27:
            return

        for key, _label, action in items:
            if key_char == key and action is not None:
                action()
                break


def category_filter_menu(stdscr, colors: tuple[Color, ...], stats: Stats) -> None:
    cats = list(CATEGORY_ORDER)
    while True:
        stdscr.erase()
        _safe_addstr(stdscr, 1, 4, "カテゴリを選んでください", curses.A_BOLD)
        for i, cat in enumerate(cats):
            count = sum(1 for c in colors if c.category == cat)
            _safe_addstr(stdscr, 3 + i, 6, f"[{i + 1}] {CATEGORY_LABEL[cat]}({count}色)")
        _safe_addstr(stdscr, 4 + len(cats), 6, "[b] 戻る")
        stdscr.refresh()

        ch = _wait_key(stdscr)
        try:
            key_char = chr(ch)
        except ValueError:
            key_char = ""

        if key_char == "b" or ch == 27:
            return
        idx = ch - ord("1")
        if 0 <= idx < len(cats):
            cat = cats[idx]
            filtered = [c for c in colors if c.category == cat]
            practice_screen(stdscr, filtered, stats, None, category_label=CATEGORY_LABEL[cat])
            return


def _ask_question(stdscr, question, question_no: int, category_label: str | None):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    has_color = curses.has_colors()
    target = question.target

    header = f"{KIND_LABEL[question.kind]}  第{question_no}問"
    if category_label:
        header += f"({category_label})"
    _safe_addstr(stdscr, 1, 4, header, curses.A_BOLD)

    row = 3
    if question.kind == "name":
        _safe_addstr(stdscr, row, 4, "この色の名前はどれでしょう?")
        row += 1
        if has_color:
            _draw_swatch(stdscr, row, 6, 24, 3, target.hex)
            row += 4
        else:
            _safe_addstr(stdscr, row, 6, f"(この端末は色を表示できません。カラーコード: {target.hex})", curses.A_DIM)
            row += 2
    else:
        label = "特徴" if question.kind == "description" else "トリビア"
        _safe_addstr(stdscr, row, 4, f"「{target.name}」({target.yomi})の{label}として正しいものはどれでしょう?")
        row += 1
        if has_color:
            _draw_swatch(stdscr, row, 6, 12, 2, target.hex)
            row += 3
        else:
            _safe_addstr(stdscr, row, 6, f"カラーコード: {target.hex}", curses.A_DIM)
            row += 2

    row += 1
    for i, text in enumerate(question.choices):
        wrapped = _wrap_to_width(text, max(1, w - 12))
        _safe_addstr(stdscr, row, 6, f"[{i + 1}]", curses.A_BOLD)
        for j, line in enumerate(wrapped):
            _safe_addstr(stdscr, row + j, 10, line)
        row += max(1, len(wrapped)) + 1

    _safe_addstr(stdscr, min(row, h - 2), 4, "[1-4] 選択    [s] スキップ    [q] メニューに戻る", curses.A_DIM)
    stdscr.refresh()

    while True:
        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return _QUIT
        if ch == ord("s"):
            return _SKIP
        if ord("1") <= ch <= ord("4"):
            idx = ch - ord("1")
            if idx < len(question.choices):
                return idx


def practice_screen(
    stdscr,
    colors: tuple[Color, ...],
    stats: Stats,
    kind: str | None,
    category_label: str | None = None,
    weak_only: bool = False,
) -> None:
    pool = list(colors)
    if weak_only:
        weak = stats.weakest(colors, limit=15)
        if len(weak) >= 8:
            pool = [c for _acc, _total, c in weak]

    question_no = 0
    while True:
        question_no += 1
        actual_kind = kind if kind is not None else random.choice(QUESTION_KINDS)
        question = make_question(tuple(pool), stats, actual_kind)

        answer = _ask_question(stdscr, question, question_no, category_label)
        if answer == _QUIT:
            return
        if answer == _SKIP:
            continue

        result = grade(question, answer)
        stats.record(question.target.name, result.correct)
        stats.save()
        _show_result(stdscr, result)


def _show_result(stdscr, result) -> None:
    question = result.question
    target = question.target
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    color = curses.color_pair(1) if result.correct else curses.color_pair(2)
    verdict = "正解!" if result.correct else "不正解"
    _safe_addstr(stdscr, 1, 4, verdict, curses.A_BOLD | color)
    if result.selected_index is not None:
        _safe_addstr(stdscr, 2, 4, f"あなたの解答: {question.choices[result.selected_index]}")

    row = 4
    _safe_addstr(stdscr, row, 4, f"正解: {target.name}({target.yomi})", curses.A_BOLD)
    row += 1
    if curses.has_colors():
        _draw_swatch(stdscr, row, 6, 12, 2, target.hex)
        row += 3
    else:
        _safe_addstr(stdscr, row, 6, f"カラーコード: {target.hex}", curses.A_DIM)
        row += 2

    _safe_addstr(stdscr, row, 4, "特徴:")
    row += 1
    for line in _wrap_to_width(target.description, max(1, w - 10)):
        _safe_addstr(stdscr, row, 6, line)
        row += 1

    row += 1
    _safe_addstr(stdscr, row, 4, "トリビア:")
    row += 1
    for line in _wrap_to_width(target.trivia, max(1, w - 10)):
        _safe_addstr(stdscr, row, 6, line)
        row += 1

    _safe_addstr(stdscr, min(row + 1, h - 2), 4, "何かキーを押すと次の問題へ進みます。", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def browse_screen(stdscr, colors: tuple[Color, ...]) -> None:
    ordered = sorted(colors, key=lambda c: (CATEGORY_ORDER.index(c.category), c.name))
    lines: list[tuple[str, str | None, bool]] = []
    current_cat = None
    for c in ordered:
        if c.category != current_cat:
            current_cat = c.category
            lines.append((f"── {CATEGORY_LABEL[current_cat]} ──", None, True))
        lines.append((f"{c.name}({c.yomi})  {c.hex}", c.hex, False))

    has_color = curses.has_colors()
    top = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        body_height = h - 3
        _safe_addstr(stdscr, 0, 2, "一覧表示(j/k または ↑↓ でスクロール、q で戻る)", curses.A_BOLD)
        for i in range(body_height):
            idx = top + i
            if idx >= len(lines):
                break
            text, hex_code, is_header = lines[idx]
            y = 2 + i
            if is_header:
                _safe_addstr(stdscr, y, 2, text, curses.A_BOLD)
                continue
            if has_color and hex_code:
                _draw_swatch(stdscr, y, 2, 2, 1, hex_code)
            _safe_addstr(stdscr, y, 5, text)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return
        if ch in (ord("j"), curses.KEY_DOWN):
            top = min(top + 1, max(0, len(lines) - body_height))
        elif ch in (ord("k"), curses.KEY_UP):
            top = max(top - 1, 0)
        elif ch == curses.KEY_NPAGE:
            top = min(top + body_height, max(0, len(lines) - body_height))
        elif ch == curses.KEY_PPAGE:
            top = max(top - body_height, 0)


def stats_screen(stdscr, colors: tuple[Color, ...], stats: Stats) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    correct, wrong = stats.totals()
    total = correct + wrong
    _safe_addstr(stdscr, 1, 4, "成績", curses.A_BOLD)
    if total == 0:
        _safe_addstr(stdscr, 3, 4, "まだ出題記録がありません。")
    else:
        _safe_addstr(stdscr, 3, 4, f"総合: {correct}/{total} 正解 ({correct / total * 100:.1f}%)")
        _safe_addstr(stdscr, 5, 4, "苦手な色 (正答率が低い順):", curses.A_BOLD)
        weak = stats.weakest(colors, limit=max(1, min(10, h - 8)))
        if not weak:
            _safe_addstr(stdscr, 6, 4, "(十分な出題回数のある色がまだありません)")
        for i, (acc, cnt, c) in enumerate(weak):
            _safe_addstr(
                stdscr,
                6 + i,
                6,
                f"{c.name}({c.yomi})  正答率{acc * 100:.0f}%({cnt}回出題)",
            )
    _safe_addstr(stdscr, h - 2, 4, "何かキーを押すと戻ります。", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def reset_stats_screen(stdscr, stats: Stats) -> None:
    stdscr.erase()
    _safe_addstr(stdscr, 1, 4, "成績をリセットしますか? (y/N)", curses.A_BOLD)
    stdscr.refresh()
    ch = stdscr.getch()
    if ch in (ord("y"), ord("Y")):
        stats.reset()
        stats.save()
        _safe_addstr(stdscr, 3, 4, "リセットしました。何かキーを押してください。")
        stdscr.refresh()
        stdscr.getch()


def run(stdscr, stats_path=DEFAULT_STATS_PATH) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        for const in _BASE_RGB:
            curses.init_pair(3 + const, curses.COLOR_BLACK, const)

    colors = load_colors()
    stats = Stats.load(stats_path)
    main_menu(stdscr, colors, stats)


def main(stats_path=DEFAULT_STATS_PATH) -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(run, stats_path=stats_path)
