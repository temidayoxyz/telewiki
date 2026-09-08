"""Tests for the quiz engine — pure logic, no network."""

import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from telewiki.quiz import (
    Question,
    QuizEngine,
    build_year_question,
    decode_answer,
    encode_answer,
    load_bank,
    new_quiz_id,
)

BANK_PATH = Path(__file__).resolve().parent.parent / "telewiki" / "data" / "questions.json"


def make_event(year, text="test event"):
    return SimpleNamespace(year=year, text=text, url="https://example.com")


class YearQuestionTests(unittest.TestCase):
    def test_invariants(self):
        rng = random.Random(42)
        q = build_year_question("first moon landing", 1969, rng=rng)
        self.assertEqual(len(q.options), 4)
        self.assertEqual(len(set(q.options)), 4)
        self.assertIn("1969", q.options)
        self.assertEqual(q.options[q.correct_index], "1969")
        self.assertIn("1969", q.explanation)
        self.assertEqual(q.tag, "on this day")

    def test_deterministic_with_seed(self):
        q1 = build_year_question("e", 1900, rng=random.Random(7))
        q2 = build_year_question("e", 1900, rng=random.Random(7))
        self.assertEqual(q1.options, q2.options)
        self.assertEqual(q1.correct_index, q2.correct_index)

    def test_wrong_years_are_plausible(self):
        q = build_year_question("e", 2000, rng=random.Random(1))
        years = [int(o) for o in q.options]
        self.assertTrue(all(y > 0 for y in years))
        self.assertTrue(all(abs(y - 2000) <= 30 for y in years if y != 2000))


class BankTests(unittest.TestCase):
    def test_bundled_bank_loads_and_validates(self):
        bank = load_bank(str(BANK_PATH))
        self.assertGreaterEqual(len(bank), 10)
        for q in bank:
            self.assertTrue(q.text)
            self.assertTrue(q.explanation)

    def test_invalid_entry_rejected(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump([{"text": "broken", "options": ["a"], "answer": 5}], fh)
            path = fh.name
        with self.assertRaises(ValueError):
            load_bank(path)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.bank = load_bank(str(BANK_PATH))
        self.engine = QuizEngine(self.bank)

    def test_topic_match_uses_event(self):
        events = [make_event(1969, "Apollo 11 moon landing"), make_event(1989, "Berlin Wall")]
        q = self.engine.next_question(events=events, topic="moon", rng=random.Random(3))
        self.assertEqual(q.tag, "on this day")
        self.assertIn("1969", q.options[q.correct_index])

    def test_topic_miss_falls_back_to_bank(self):
        events = [make_event(1969, "Apollo 11 moon landing")]
        q = self.engine.next_question(events=events, topic="zzz-no-match", rng=random.Random(3))
        self.assertIn(q, self.bank)

    def test_no_events_uses_bank(self):
        q = self.engine.next_question(rng=random.Random(3))
        self.assertIn(q, self.bank)

    def test_events_without_year_use_bank(self):
        events = [SimpleNamespace(year=None, text="undated", url=None)]
        q = self.engine.next_question(events=events, rng=random.Random(3))
        self.assertIn(q, self.bank)

    def test_empty_bank_rejected(self):
        with self.assertRaises(ValueError):
            QuizEngine([])


class CodecTests(unittest.TestCase):
    def test_roundtrip(self):
        qid = new_quiz_id()
        self.assertEqual(decode_answer(encode_answer(qid, 2)), (qid, 2))

    def test_malformed(self):
        for bad in ["", "qz", "qz::", "xx:abcd:1", "qz:abcd:x", "qz:ab:1:2"]:
            self.assertIsNone(decode_answer(bad), bad)


class QuestionValidationTests(unittest.TestCase):
    def test_rejects_bad_questions(self):
        with self.assertRaises(ValueError):
            Question("t", ["only-one"], 0, "e")
        with self.assertRaises(ValueError):
            Question("t", ["a", "b"], 2, "e")
        with self.assertRaises(ValueError):
            Question("t", ["a", "a"], 0, "e")


class SessionTests(unittest.TestCase):
    def setUp(self):
        from telewiki.handlers import quiz as quiz_handlers

        self.h = quiz_handlers
        self.h.SESSIONS.clear()

    def tearDown(self):
        self.h.SESSIONS.clear()

    def test_start_in_stop_cycle(self):
        self.assertFalse(self.h.in_session(1))
        self.h.start_session(1, "space")
        self.assertTrue(self.h.in_session(1))
        self.assertEqual(self.h.session_topic(1), "space")
        self.assertTrue(self.h.end_session(1))
        self.assertFalse(self.h.in_session(1))

    def test_end_missing_session(self):
        self.assertFalse(self.h.end_session(999))

    def test_none_topic_session_counts(self):
        self.h.start_session(2, None)
        self.assertTrue(self.h.in_session(2))
        self.assertIsNone(self.h.session_topic(2))
        self.assertTrue(self.h.end_session(2))

    def test_help_documents_stop(self):
        from telewiki.handlers.start import HELP_TEXT, MENU_TEXT

        self.assertIn("/stop", HELP_TEXT)
        self.assertIn("/quiz", MENU_TEXT)
        self.assertIn("/wiki", MENU_TEXT)
        self.assertIn("/digest", MENU_TEXT)


if __name__ == "__main__":
    unittest.main()
