"""出題ロジック(curses に依存しない純粋なロジック)。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from iroquiz.data import Color
from iroquiz.stats import Stats

QUESTION_KINDS = ("name", "description", "trivia")

KIND_LABEL = {
    "name": "色名当てクイズ",
    "description": "特徴当てクイズ",
    "trivia": "トリビア当てクイズ",
}


def weighted_choice(colors: list[Color], stats: Stats) -> Color:
    """正答率が低い色ほど出題されやすくなるように重み付けして1色選ぶ。"""
    weights = []
    for c in colors:
        correct, wrong = stats.record_for(c.name)
        total = correct + wrong
        if total == 0:
            weight = 3.0
        else:
            accuracy = correct / total
            weight = 1.0 + (1.0 - accuracy) * 4.0
        weights.append(weight)
    return random.choices(colors, weights=weights, k=1)[0]


@dataclass
class Question:
    kind: str
    target: Color
    choices: list[str]
    correct_index: int


def _field(kind: str, color: Color) -> str:
    return color.name if kind == "name" else getattr(color, kind)


def make_question(colors: tuple[Color, ...], stats: Stats, kind: str) -> Question:
    """出題プールから1色選び、その周辺色も含めた4択問題を作る。

    紛らわしい(=学習効果の高い)誤答選択肢にするため、可能な限り正解と
    同じカテゴリの色を優先して誤答候補に採用する。
    """
    target = weighted_choice(list(colors), stats)
    others = [c for c in colors if c.name != target.name]

    same_category = [c for c in others if c.category == target.category]
    random.shuffle(same_category)
    rest = [c for c in others if c.category != target.category]
    random.shuffle(rest)
    distractors = (same_category + rest)[:3]

    pool = distractors + [target]
    random.shuffle(pool)
    choices = [_field(kind, c) for c in pool]
    correct_index = next(i for i, c in enumerate(pool) if c.name == target.name)

    return Question(kind=kind, target=target, choices=choices, correct_index=correct_index)


@dataclass
class RoundResult:
    question: Question
    selected_index: int | None
    correct: bool


def grade(question: Question, selected_index: int) -> RoundResult:
    return RoundResult(
        question=question,
        selected_index=selected_index,
        correct=selected_index == question.correct_index,
    )
