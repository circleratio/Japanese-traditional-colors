# 日本の伝統色クイズ 設計仕様書

対象: `requirement.md` に記載した要求を満たす実装(`iroquiz/` パッケージ)
の設計内容をまとめたもの。

## 1. アーキテクチャ概要

`kimariji/` と同様、依存ライブラリを増やさず標準ライブラリのみで完結
させるため、「ロジック層」と「表示(curses)層」を分離している。
ロジック層は curses に一切依存せず、TTY なしでも import・単体実行
できる。

```
iroquiz/
├── __init__.py        パッケージ宣言のみ
├── __main__.py         CLI エントリポイント(argparse)
├── data.py              伝統色データのロード(Color データクラス)
├── data/
│   └── colors.json       36色分のデータ本体
├── quiz.py               出題ロジック(4択問題の作成・重み付け抽選・採点)
├── stats.py              成績の永続化(JSON ファイル読み書き)
└── tui.py                curses による画面描画・入力処理
```

依存関係の向き: `tui.py` → `quiz.py` / `stats.py` / `data.py`。
`quiz.py` は `stats.py` の `Stats` を型として参照するのみで、curses
には一切依存しない。

## 2. データ設計

### 2.1 データソース

各色の名前・読み・カラーコード(近似値)・特徴・トリビアは、日本の
伝統色に関して広く知られている一般的な内容(染料・顔料の由来、歴史的
な用途、文学作品での言及など)をもとにまとめた。カラーコードは、
染料・顔料が実現する色味の目安を示す近似値であり、厳密な測色値では
ない(`requirement.md` 6章にも明記)。

カテゴリ(`category`)は赤系・橙系・黄系・緑系・青系・紫系・
白黒鼠系の7区分とし、色相の近さによる大まかな分類とした(植物学・
色彩工学的に厳密な分類ではなく、出題の絞り込みと誤答選択肢の
紛らわしさ調整のための実用的な区分)。

内訳: 赤系6・橙系5・黄系5・緑系6・青系7・紫系4・白黒鼠系3 の
計36色。

### 2.2 データスキーマ

`iroquiz/data/colors.json` は以下の形式のオブジェクトを36件含む
JSON 配列。

```json
{
  "name": "萌黄色",
  "yomi": "もえぎいろ",
  "hex": "#AACF53",
  "category": "green",
  "description": "春先に萌え出る若葉のような、黄みを帯びた明るい緑色。",
  "trivia": "源義経の鎧の威毛(おどしげ)の色として知られ、若々しさの象徴とされた。"
}
```

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `name` | str | 色名(漢字) |
| `yomi` | str | 色名の読み(ひらがな) |
| `hex` | str | カラーコード(`#RRGGBB`、目安の近似値) |
| `category` | str | カテゴリキー(`red`/`orange`/`yellow`/`green`/
  `blue`/`purple`/`neutral`のいずれか) |
| `description` | str | 特徴(由来・色味の説明) |
| `trivia` | str | トリビア(歴史・文学・風習等の豆知識) |

### 2.3 `data.py`

- `Color`: 上記スキーマに対応する `@dataclass(frozen=True)`。
- `CATEGORY_LABEL`: カテゴリキー → 日本語表示ラベルの辞書。
- `CATEGORY_ORDER`: カテゴリの表示順序(`CATEGORY_LABEL` のキー順)。
- `load_colors() -> tuple[Color, ...]`: JSON を読み込み `Color` の
  タプルを返す。`functools.lru_cache(maxsize=1)` によりプロセス内
  では1度だけファイルを読み込む。

## 3. 出題ロジック設計(`quiz.py`)

curses に依存しない純粋関数として実装し、`tui.py` から呼び出される。

- `QUESTION_KINDS = ("name", "description", "trivia")`: 出題種別。
- `KIND_LABEL`: 出題種別 → 日本語ラベルの辞書(メニュー・見出し表示用)。
- `weighted_choice(colors, stats) -> Color`: 出題プールから1色を
  重み付き乱択で選ぶ。
  - 出題実績がない色: 重み `3.0`。
  - 出題実績がある色: 重み `1.0 + (1.0 - 正答率) * 4.0`
    (正答率が低いほど重みが大きい。正答率100%でも最低重み1.0は
    残るため、完全に出題対象から外れることはない)。
  - `random.choices(..., weights=...)` により選択。
- `Question`(`@dataclass`): `kind` / `target`(正解の `Color`) /
  `choices`(シャッフル済みの4択テキスト) / `correct_index`
  (シャッフル後の正解インデックス)を保持する。
- `make_question(colors, stats, kind) -> Question`:
  1. `weighted_choice` で出題対象の色(`target`)を1色選ぶ。
  2. `target` 以外の色から誤答候補を作る。まず `target` と同じ
     `category` の色を優先し、それだけで3件に満たない場合は他の
     カテゴリの色で補う。いずれもランダムな順序で採用する。
  3. `kind` に応じて表示テキストを決める(`kind == "name"` なら
     `Color.name`、それ以外は `getattr(color, kind)`)。
  4. 正解1件+誤答3件、計4件をシャッフルし、`choices` と
     `correct_index` を確定する。
- `RoundResult`(`@dataclass`): `question` / `selected_index`
  (ユーザーが選んだ選択肢のインデックス、スキップ時は無効)/
  `correct`(正誤)を保持する。
- `grade(question, selected_index) -> RoundResult`:
  `selected_index == question.correct_index` であれば正解と判定
  する。

## 4. 成績永続化設計(`stats.py`)

`kimariji/stats.py` と同様の設計。キーを歌番号(int)ではなく色名
(str)にしている点のみ異なる。

- 保存形式は JSON。トップレベルは色名をキーとする辞書で、値は
  `{"correct": int, "wrong": int}`。
- 既定の保存先は `~/.iroquiz_stats.json`(`DEFAULT_STATS_PATH`)。
  `iroquiz/__main__.py` の `--state-file` オプションで変更可能。
- `Stats.load(path)`: ファイルが存在しない、または壊れている場合は
  空の状態から開始する(エラーで落とさない)。
- `Stats.record(name, correct)`: 該当色の `correct`/`wrong` を
  1加算。
- `Stats.save()`: 現在の状態をファイルへ書き出す。出題1問ごと
  (解答直後)に呼び出し、都度永続化する。
- `Stats.totals()`: 全体の正解数・不正解数を返す。
- `Stats.weakest(colors, limit)`: 出題実績が1回以上ある色のみを
  対象に、正答率の低い順(同率の場合は出題回数が多い順)に並べ替え、
  上位 `limit` 件を返す。
- `Stats.reset()`: 内部状態を空にする(呼び出し側で `save()` する
  までファイルには反映されない)。

## 5. UI 設計(`tui.py`)

### 5.1 画面遷移

```
main_menu
 ├─ [1] practice_screen(colors 全体, kind="name")
 ├─ [2] practice_screen(colors 全体, kind="description")
 ├─ [3] practice_screen(colors 全体, kind="trivia")
 ├─ [4] category_filter_menu → practice_screen(カテゴリで絞った colors, kind=None)
 ├─ [5] practice_screen(苦手上位15色プール, kind=None, weak_only)
 ├─ [6] browse_screen
 ├─ [7] stats_screen
 ├─ [8] reset_stats_screen
 └─ [q] 終了
```

`kind=None` の出題(カテゴリ指定・苦手優先)では、設問ごとに
`QUESTION_KINDS` からランダムに出題種別を選ぶ(色名・特徴・トリビアを
まんべんなく学習できるようにするため)。

各画面はブロッキングな `while` ループで構成し、ユーザー操作で
`return` することで呼び出し元へ戻る(画面遷移スタックは Python の
関数呼び出しスタックそのものを利用する)。

### 5.2 出題画面のフロー(`_ask_question` / `practice_screen`)

1. `make_question` で1問作成する。
2. `kind == "name"` の場合は色見本(スウォッチ)のみを表示し色名を
   隠す。`kind` が `"description"`/`"trivia"` の場合は色名・読みを
   表示し(小さめの色見本も添える)、特徴/トリビアの4択を選ばせる。
3. 4択は `[1]`〜`[4]` に番号付けして縦に並べる。1つの選択肢が
   端末幅に収まらない場合は `_wrap_to_width` で複数行に折り返す。
4. キー入力は `stdscr.getch()` で待ち受ける。
   - `1`〜`4`: その番号の選択肢で解答を確定する。
   - `s`: この問題をスキップする(不正解としては記録しない)。
   - `q` または ESC: 出題モードを終了しメニューへ戻る。
5. スキップ以外の場合、`grade(question, selected_index)` で採点し
   `stats.record()` / `stats.save()` を行った上で `_show_result()`
   を表示する。
6. `_show_result()` は正誤に関わらず、正解の色名・色見本・特徴・
   トリビアをまとめて表示する。何かキーが押されたら次の問題へ進む。

`weak_only=True` の場合は、`stats.weakest()` の上位15色を出題プール
とする。15色未満(学習初期で出題実績が少ない)場合は通常の全体
プールにフォールバックする。

### 5.3 一覧表示画面(`browse_screen`)

- 表示対象の色を `(カテゴリの表示順, 色名)` でソートし、カテゴリが
  変わるタイミングでグループ見出し行(例: `── 青系 ──`)を挿入した
  行リストを事前に構築する。
- 各行は、カラー対応端末では色見本(2カラム)+色名(読み)+カラー
  コードを、非対応端末では色見本を省略してテキストのみを表示する。
- スクロールは表示開始行インデックス `top` を保持し、`j`/`↓` で+1、
  `k`/`↑` で-1、PageDown/PageUp で画面の行数分だけ移動する。`top`
  は `[0, len(lines) - body_height]` の範囲にクランプする。

### 5.4 全角文字対応・テキスト折り返し

`kimariji/tui.py` と同じ `_char_width` / `_display_width` /
`_truncate_to_width` / `_safe_addstr` を用いて、全角文字(漢字・
ひらがな)の表示幅を正しく扱い、範囲外描画や `curses.error` による
クラッシュを防ぐ。

加えて、特徴・トリビアの文章は1行に収まらないことが多いため、
`_wrap_to_width(text, max_width)` で表示カラム数を基準に貪欲法で
複数行へ折り返す(日本語には単語区切りの空白がないため、単語境界を
考慮しない単純な文字単位の折り返しとする)。

### 5.5 色見本(スウォッチ)の描画

curses の `init_color`/`can_change_color` は対応端末が限られ移植性
が低いため、より広く動作する方式として、色見本は curses が標準で
持つ8色(`COLOR_BLACK`〜`COLOR_WHITE`)のうち、対象のカラーコードに
最も近い1色を背景色として塗りつぶす方式で近似表示する。

- `_hex_to_rgb(hex_code)`: `#RRGGBB` を `(R, G, B)` に変換する。
- `_BASE_RGB`: curses の8色それぞれに対応する代表 RGB 値の辞書。
- `_nearest_base_color(hex_code)`: 対象の RGB と `_BASE_RGB` の
  各色とのユークリッド距離を比較し、最も近い curses 色定数を返す。
- `_swatch_pair(hex_code)`: `3 + _nearest_base_color(hex_code)` を
  色ペア番号として返す(ペア1・2は正解/不正解の見出し色に使用
  済みのため、スウォッチ用は3番以降を使う)。
- `_draw_swatch(win, y, x, width, height, hex_code)`: 対応する
  色ペアを背景色にした空白文字を矩形に描画する(前景色は空白しか
  描画しないため実質無関係)。
- 色ペアの初期化は起動時(`run()`)に一度だけ、`curses.has_colors()`
  が真の場合のみ行う。カラー非対応端末では、出題・結果・一覧の
  各画面ともカラーコードのテキスト表示にフォールバックする。
- 8色への丸め込みのため、似た中間色同士(例: 群青色と紺色)が同じ
  背景色で表示されることがあるが、これは移植性を優先した設計上の
  制約として許容する(`requirement.md` 5章の「カラー対応端末では
  実際の色に近い形で表示する」は目安表示として満たされる)。

### 5.6 色・装飾

- 正解=緑(`color_pair(1)`)、不正解=赤(`color_pair(2)`)を
  `curses.has_colors()` の場合のみ初期化して結果画面の見出しに
  使用する。カラー非対応端末でも `A_BOLD` 等の属性のみで機能する。

### 5.7 ロケール・エントリポイント

- `main(stats_path)`: `locale.setlocale(locale.LC_ALL, "")` を実行
  して実行環境のロケールに合わせた文字幅処理・エンコーディングを
  有効化した上で、`curses.wrapper(run, ...)` を呼び出す。
  `curses.wrapper` は端末初期化・後始末(`curs_set` の復元、
  `endwin()` 等)を保証し、例外発生時にも端末を壊れた状態のまま
  残さない。
- `run(stdscr, stats_path)`: カーソル非表示化、特殊キー(矢印キー等)
  の有効化、色ペアの初期化、データ・成績のロードを行い、
  `main_menu` を呼び出す。

## 6. CLI 設計(`__main__.py`)

```
python -m iroquiz [--state-file PATH]
```

- `--state-file`: 成績保存先のパス(既定値: `stats.DEFAULT_STATS_PATH`
  = `~/.iroquiz_stats.json`)。リポジトリ内の既存ツール
  (`monitor_notified_bodies.py`、`kimariji`)が `--state-file`
  オプションで状態ファイルを指定する規約と揃えている。

## 7. エラー処理・堅牢性についての設計方針

- 成績ファイルの読み込み失敗(存在しない・壊れている)はアプリの
  起動を妨げず、空の成績として扱う。
- 画面描画は全て `_safe_addstr`(またはそれを内部で使う
  `_draw_swatch`)を経由させることで、ウィンドウ範囲外への書き込み
  や、想定より小さい端末サイズによる `curses.error` でアプリ全体が
  クラッシュしないようにしている。
- キー入力は、想定外のキーコードが来ても無視されるだけで例外を
  発生させない設計とする。

## 8. テスト方針

- `data.py` / `quiz.py` / `stats.py` は curses に依存しないため、
  実端末(TTY)なしで import・関数呼び出しレベルの検証が可能。
  データ整合性(36件全てにフィールド欠落がないこと、色名の重複が
  ないこと、カテゴリキーが `CATEGORY_LABEL` の範囲内であること等)
  はこの層で検証済み。
- `tui.py` は実際のターミナル(PTY)上で `python -m iroquiz` を
  起動し、各画面への遷移・キー入力・スクロール・端末幅を変えた
  場合の表示崩れの有無を目視確認する形で検証する。
