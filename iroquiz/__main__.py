"""日本の伝統色クイズ CLI エントリポイント。

    python -m iroquiz
"""

from __future__ import annotations

import argparse
from pathlib import Path

from iroquiz.stats import DEFAULT_STATS_PATH
from iroquiz.tui import main as run_tui


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日本の伝統色クイズ")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATS_PATH,
        help=f"成績の保存先ファイル(既定: {DEFAULT_STATS_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_tui(stats_path=args.state_file)


if __name__ == "__main__":
    main()
