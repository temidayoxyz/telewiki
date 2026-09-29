"""Tests for the quiz engine — pure logic, no network."""

import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telewiki.quiz import (
    Question,
    QuizEngine,
    build_year_question,
    decode_answer,
    encode_answer,
    load_bank,
    new_quiz_id,
)
from telewiki.storage import Database

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


CHAT_ID = 42
USER_ID = 7


class _FakeBot:
    """Records every quiz question the handlers try to send."""

    def __init__(self, chat_type: str):
        self._chat_type = chat_type
        self.sent: list = []

    async def get_chat(self, chat_id):
        return SimpleNamespace(type=self._chat_type)

    async def send_message(self, chat_id, text, **kwargs):
        message = SimpleNamespace(message_id=len(self.sent) + 1, text=text, photo=None)
        self.sent.append(message)
        return message


class _FakeQuery:
    def __init__(self, data=None, message_id=1, user_id=USER_ID):
        self.data = data
        self.message = SimpleNamespace(message_id=message_id)
        self.from_user = SimpleNamespace(id=user_id, mention_html=lambda: "@user")
        self.answers: list = []
        self.edits: list = []

    async def answer(self, text=None):
        self.answers.append(text)

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)

    async def reply_text(self, text, **kwargs):
        pass


class QuizButtonSessionTests(unittest.IsolatedAsyncioTestCase):
    """'Quiz me on this' must behave like /quiz.

    The button used to send a single question and never register a session, so
    answering correctly ended the round instead of continuing.
    """

    def setUp(self):
        from telewiki.handlers import quiz as handlers

        self.h = handlers
        self.h.ACTIVE.clear()
        self.h.SESSIONS.clear()
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = Database(self._tmp.name)

    def tearDown(self):
        self.h.ACTIVE.clear()
        self.h.SESSIONS.clear()
        self.db.close()
        os.unlink(self._tmp.name)

    def _context(self, chat_type: str):
        self.bot = _FakeBot(chat_type)
        self.context = SimpleNamespace(
            bot=self.bot,
            bot_data={
                "db": self.db,
                "engine": QuizEngine(load_bank(str(BANK_PATH))),
                "wiki": SimpleNamespace(on_this_day=AsyncMock(return_value=[])),
            },
        )
        return self.context

    async def _press_quiz_button(self, chat_type: str = "private"):
        from telewiki.handlers.wiki import _quiz_topic_key

        self._context(chat_type)
        self.context.bot_data[_quiz_topic_key(CHAT_ID, USER_ID)] = "Mercury (planet)"
        query = _FakeQuery()
        await self.h.quiz_me_callback(
            SimpleNamespace(
                callback_query=query,
                effective_chat=SimpleNamespace(id=CHAT_ID, type=chat_type),
                effective_user=SimpleNamespace(id=USER_ID),
                effective_message=SimpleNamespace(reply_text=AsyncMock()),
            ),
            self.context,
        )

    async def _answer_correctly(self, chat_type: str = "private"):
        (_chat, message_id), active = next(iter(self.h.ACTIVE.items()))
        query = _FakeQuery(
            data=encode_answer(active.quiz_id, active.question.correct_index),
            message_id=message_id,
        )
        await self.h.quiz_answer_callback(
            SimpleNamespace(
                callback_query=query,
                effective_chat=SimpleNamespace(id=CHAT_ID, type=chat_type),
            ),
            self.context,
        )

    async def test_button_registers_a_session_in_a_dm(self):
        await self._press_quiz_button()
        self.assertEqual(len(self.bot.sent), 1)
        self.assertTrue(self.h.in_session(CHAT_ID))

    async def test_correct_answer_continues_the_quiz(self):
        await self._press_quiz_button()
        await self._answer_correctly()
        self.assertEqual(len(self.bot.sent), 2, "no follow-up question was sent")

    async def test_session_keeps_the_wiki_topic(self):
        await self._press_quiz_button()
        self.assertEqual(self.h.session_topic(CHAT_ID), "Mercury (planet)")
        await self._answer_correctly()
        self.assertEqual(self.h.session_topic(CHAT_ID), "Mercury (planet)")

    async def test_stop_ends_a_button_started_session(self):
        await self._press_quiz_button()
        self.assertTrue(self.h.end_session(CHAT_ID))
        self.assertFalse(self.h.in_session(CHAT_ID))

    async def test_group_button_stays_one_round(self):
        """Groups are one round at a time — no session, no follow-up question."""
        await self._press_quiz_button(chat_type="supergroup")
        self.assertFalse(self.h.in_session(CHAT_ID))
        await self._answer_correctly(chat_type="supergroup")
        self.assertEqual(len(self.bot.sent), 1)

    async def test_expired_topic_is_reported(self):
        self._context("private")  # no topic stored for this user
        query = _FakeQuery()
        await self.h.quiz_me_callback(
            SimpleNamespace(
                callback_query=query,
                effective_chat=SimpleNamespace(id=CHAT_ID, type="private"),
                effective_user=SimpleNamespace(id=USER_ID),
                effective_message=SimpleNamespace(reply_text=AsyncMock()),
            ),
            self.context,
        )
        self.assertEqual(len(self.bot.sent), 0)
        self.assertIn("expired", query.answers[0].lower())


if __name__ == "__main__":
    unittest.main()
