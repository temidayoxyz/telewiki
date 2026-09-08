"""Quiz question generation.

Pure logic — no network, no telegram imports — so the engine is fully
unit-testable. Two providers:

1. "On this day" events -> "In which year did this happen?" questions with
   plausible wrong-year distractors. Self-updating every day.
2. A bundled, hand-checked question bank (telewiki/data/questions.json).
"""

import json
import random
import secrets
from dataclasses import dataclass, field

CALLBACK_PREFIX = "qz"


@dataclass
class Question:
    text: str
    options: list
    correct_index: int
    explanation: str
    source_url: str | None = None
    tag: str = "general"

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("a question needs at least 2 options")
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError("correct_index out of range")
        if len(set(self.options)) != len(self.options):
            raise ValueError("options must be unique")

    @property
    def answer(self) -> str:
        return self.options[self.correct_index]


def build_year_question(
    event_text: str,
    year: int,
    source_url: str | None = None,
    rng: random.Random | None = None,
) -> Question:
    """Turn a dated historical event into a multiple-choice year question."""
    rng = rng or random.Random()
    wrong: set = set()
    attempts = 0
    while len(wrong) < 3 and attempts < 200:
        attempts += 1
        candidate = year + rng.choice([-1, 1]) * rng.randint(2, 30)
        if candidate > 0 and candidate != year:
            wrong.add(candidate)
    options = [year] + list(wrong)
    rng.shuffle(options)
    return Question(
        text=f"In which year did this happen?\n\n{event_text}",
        options=[str(y) for y in options],
        correct_index=options.index(year),
        explanation=f"{year} — {event_text}",
        source_url=source_url,
        tag="on this day",
    )


def load_bank(path: str) -> list:
    """Load and validate the bundled question bank."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    questions = []
    for i, item in enumerate(raw):
        try:
            questions.append(
                Question(
                    text=item["text"],
                    options=list(item["options"]),
                    correct_index=int(item["answer"]),
                    explanation=item.get("explanation", ""),
                    source_url=item.get("url"),
                    tag=item.get("tag", "general"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid question bank entry #{i}: {exc}") from exc
    if not questions:
        raise ValueError("question bank is empty")
    return questions


class QuizEngine:
    def __init__(self, bank: list):
        if not bank:
            raise ValueError("quiz engine needs a non-empty question bank")
        self._bank = bank

    def next_question(
        self,
        events: list | None = None,
        topic: str | None = None,
        rng: random.Random | None = None,
    ) -> Question:
        """Pick the next question.

        Prefers a topic-filtered "on this day" event, then any event, then
        falls back to the static bank (which is always available).
        """
        rng = rng or random.Random()
        dated = [e for e in (events or []) if getattr(e, "year", None)]
        if topic and dated:
            needle = topic.lower()
            dated = [e for e in dated if needle in (e.text or "").lower()]
        if dated:
            event = rng.choice(dated)
            return build_year_question(event.text, event.year, event.url, rng=rng)
        # No usable event (or the topic matched nothing): fall back to the
        # static bank, which is always available.
        return rng.choice(self._bank)


# -- callback payload codec (Telegram callback_data <= 64 bytes) --------------


def new_quiz_id() -> str:
    return secrets.token_hex(4)


def encode_answer(quiz_id: str, index: int) -> str:
    return f"{CALLBACK_PREFIX}:{quiz_id}:{index}"


def decode_answer(data: str) -> tuple | None:
    """Return (quiz_id, index) or None if the payload is malformed."""
    try:
        prefix, quiz_id, index = data.split(":")
    except ValueError:
        return None
    if prefix != CALLBACK_PREFIX or not quiz_id or not index.isdigit():
        return None
    return quiz_id, int(index)
