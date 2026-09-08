"""Tests for the SQLite storage layer (temporary database files)."""

import os
import tempfile
import unittest

from telewiki.storage import Database, Subscription


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = Database(self._tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self._tmp.name)

    def test_subscription_roundtrip(self):
        self.assertIsNone(self.db.get_subscription(123))
        self.db.save_subscription(Subscription(123, ["physics"], "08:00", True))
        sub = self.db.get_subscription(123)
        self.assertEqual(sub.topics, ["physics"])
        self.assertEqual(sub.time, "08:00")
        self.assertTrue(sub.enabled)

    def test_subscription_update_and_delete(self):
        self.db.save_subscription(Subscription(1, ["a"], "08:00", True))
        self.db.save_subscription(Subscription(1, ["a", "b"], "09:30", False))
        sub = self.db.get_subscription(1)
        self.assertEqual(sub.topics, ["a", "b"])
        self.assertEqual(sub.time, "09:30")
        self.assertFalse(sub.enabled)
        self.db.delete_subscription(1)
        self.assertIsNone(self.db.get_subscription(1))

    def test_list_subscriptions_filters_disabled(self):
        self.db.save_subscription(Subscription(1, ["a"], "08:00", True))
        self.db.save_subscription(Subscription(2, ["b"], "08:00", False))
        self.assertEqual(len(self.db.list_subscriptions(enabled_only=True)), 1)
        self.assertEqual(len(self.db.list_subscriptions(enabled_only=False)), 2)

    def test_scoring_math(self):
        s = self.db.record_result(7, 100, True)  # streak 0 -> +10
        self.assertEqual((s["points"], s["streak"], s["correct"], s["answered"]), (10, 1, 1, 1))
        s = self.db.record_result(7, 100, True)  # streak 1 -> +12
        self.assertEqual((s["points"], s["streak"]), (22, 2))
        s = self.db.record_result(7, 100, False)  # streak reset
        self.assertEqual((s["points"], s["streak"], s["answered"]), (22, 0, 3))

    def test_streak_bonus_caps(self):
        for _ in range(10):
            s = self.db.record_result(9, 100, True)
        # gains: 10,12,14,16,18,20 then 20 each -> 10+12+14+16+18+20*5 = 170
        self.assertEqual(s["points"], 170)
        self.assertEqual(s["streak"], 10)

    def test_scores_are_per_chat(self):
        self.db.record_result(7, 100, True)
        other = self.db.get_score(7, 200)
        self.assertEqual(other["points"], 0)

    def test_leaderboard_order(self):
        self.db.record_result(1, 100, True)
        self.db.record_result(2, 100, True)
        self.db.record_result(2, 100, True)
        board = self.db.leaderboard(100)
        self.assertEqual([r["user_id"] for r in board], [2, 1])
        self.assertEqual(board[0]["points"], 22)


if __name__ == "__main__":
    unittest.main()
