"""Tests for the SQLite storage layer (temporary database files)."""

import os
import sqlite3
import tempfile
import unittest

from telewiki.storage import EXPECTED_COLUMNS, Database, Subscription


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


class MigrationTests(unittest.TestCase):
    """A column added in a release must reach databases created before it.

    CREATE TABLE IF NOT EXISTS silently ignores a new column on an existing
    table, which turns a deploy into a runtime "no such column" crash.
    """

    # Genuinely older: `answered` and `time`/`enabled` did not exist yet, so
    # _migrate() has real work to do. CREATE TABLE IF NOT EXISTS leaves these
    # tables alone, which is the whole point.
    LEGACY_SCORES = """
        CREATE TABLE scores (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            points   INTEGER NOT NULL DEFAULT 0,
            streak   INTEGER NOT NULL DEFAULT 0,
            correct  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    """
    LEGACY_SUBSCRIPTIONS = """
        CREATE TABLE subscriptions (
            chat_id INTEGER PRIMARY KEY,
            topics  TEXT NOT NULL DEFAULT '[]'
        )
    """

    def _legacy_db(self):
        """A pre-migration database that already holds real user data."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.executescript(self.LEGACY_SCORES)
        conn.executescript(self.LEGACY_SUBSCRIPTIONS)
        conn.execute(
            "INSERT INTO scores (user_id, chat_id, points, streak, correct) "
            "VALUES (7, 42, 22, 2, 2)"
        )
        conn.execute("INSERT INTO subscriptions (chat_id, topics) VALUES (42, '[\"physics\"]')")
        conn.commit()
        conn.close()
        return tmp.name

    def _columns(self, db, table):
        return {row["name"] for row in db._conn.execute(f"PRAGMA table_info({table})")}

    def test_fresh_database_has_every_expected_column(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = Database(tmp.name)
        try:
            for table, columns in EXPECTED_COLUMNS.items():
                self.assertTrue(
                    columns.keys() <= self._columns(db, table),
                    f"{table} missing {columns.keys() - self._columns(db, table)}",
                )
        finally:
            db.close()
            os.unlink(tmp.name)

    def test_legacy_database_gains_the_missing_columns(self):
        path = self._legacy_db()
        self.addCleanup(os.unlink, path)
        db = Database(path)
        try:
            for table, columns in EXPECTED_COLUMNS.items():
                missing = set(columns) - self._columns(db, table)
                self.assertFalse(missing, f"{table} still missing {missing}")
        finally:
            db.close()

    def test_migration_preserves_existing_rows(self):
        path = self._legacy_db()
        self.addCleanup(os.unlink, path)
        db = Database(path)
        try:
            score = db.get_score(7, 42)
            self.assertEqual(score["points"], 22)
            self.assertEqual(score["streak"], 2)
            self.assertEqual(score["correct"], 2)
            sub = db.get_subscription(42)
            self.assertEqual(sub.topics, ["physics"])
        finally:
            db.close()

    def test_new_column_defaults_to_its_default_for_old_rows(self):
        """A row written before the column existed reads back as the default."""
        path = self._legacy_db()
        self.addCleanup(os.unlink, path)
        db = Database(path)
        try:
            self.assertEqual(db.get_score(7, 42)["answered"], 0)
            sub = db.get_subscription(42)
            self.assertEqual(sub.time, "08:00")
            self.assertTrue(sub.enabled)
        finally:
            db.close()

    def test_migration_is_idempotent(self):
        """Opening the same database repeatedly must not raise or duplicate."""
        path = self._legacy_db()
        self.addCleanup(os.unlink, path)
        for _ in range(3):
            Database(path).close()
        db = Database(path)
        try:
            self.assertEqual(db.get_score(7, 42)["points"], 22)
        finally:
            db.close()

    def test_migrated_database_still_writes(self):
        path = self._legacy_db()
        self.addCleanup(os.unlink, path)
        db = Database(path)
        try:
            db.record_result(7, 42, True)
            self.assertEqual(db.get_score(7, 42)["answered"], 1)
            db.save_subscription(Subscription(42, ["physics", "space"], "09:30", False))
            sub = db.get_subscription(42)
            self.assertEqual(sub.topics, ["physics", "space"])
            self.assertEqual(sub.time, "09:30")
        finally:
            db.close()

    def test_expected_columns_are_additive_safe(self):
        """Every declared column must be nullable or carry a DEFAULT."""
        for table, columns in EXPECTED_COLUMNS.items():
            for name, decl in columns.items():
                upper = decl.upper()
                self.assertTrue(
                    "NOT NULL" not in upper or "DEFAULT" in upper,
                    f"{table}.{name} is NOT NULL without a DEFAULT; "
                    "SQLite cannot ADD COLUMN that",
                )


if __name__ == "__main__":
    unittest.main()
