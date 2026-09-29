"""SQLite persistence for TeleWiki: digest subscriptions and quiz scores."""

import json
import logging
import sqlite3
from dataclasses import dataclass

log = logging.getLogger(__name__)

# The shape every table is expected to have.
#
# CREATE TABLE IF NOT EXISTS will not alter a table that already exists, so a
# column added to _init_schema is silently ignored on any database created
# before it — the new code then fails at runtime with "no such column", long
# after the deploy reported itself healthy. _migrate() walks this and adds
# whatever is missing, so an additive change reaches live databases on deploy
# and existing rows keep their data.
#
# Additive only. Every column must be nullable or carry a DEFAULT, because
# SQLite cannot ADD COLUMN ... NOT NULL without one. Widening, renaming or
# dropping a column needs a table rebuild that copies rows — that is a
# deliberate, hand-written migration, not something to do automatically.
EXPECTED_COLUMNS: dict = {
    "subscriptions": {
        "chat_id": "INTEGER",
        "topics": "TEXT NOT NULL DEFAULT '[]'",
        "time": "TEXT NOT NULL DEFAULT '08:00'",
        "enabled": "INTEGER NOT NULL DEFAULT 1",
    },
    "scores": {
        "user_id": "INTEGER",
        "chat_id": "INTEGER",
        "points": "INTEGER NOT NULL DEFAULT 0",
        "streak": "INTEGER NOT NULL DEFAULT 0",
        "correct": "INTEGER NOT NULL DEFAULT 0",
        "answered": "INTEGER NOT NULL DEFAULT 0",
    },
}


@dataclass
class Subscription:
    chat_id: int
    topics: list
    time: str  # HH:MM, UTC
    enabled: bool


# Scoring: base points for a correct answer plus a streak bonus (capped).
BASE_POINTS = 10
STREAK_BONUS = 2
MAX_STREAK_BONUS = 5


class Database:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._migrate()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    chat_id INTEGER PRIMARY KEY,
                    topics  TEXT NOT NULL DEFAULT '[]',
                    time    TEXT NOT NULL DEFAULT '08:00',
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS scores (
                    user_id  INTEGER NOT NULL,
                    chat_id  INTEGER NOT NULL,
                    points   INTEGER NOT NULL DEFAULT 0,
                    streak   INTEGER NOT NULL DEFAULT 0,
                    correct  INTEGER NOT NULL DEFAULT 0,
                    answered INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                );
                """
            )

    def _migrate(self) -> None:
        """Add any column in EXPECTED_COLUMNS that an existing table lacks.

        CREATE TABLE IF NOT EXISTS leaves an existing table untouched, so this
        is what makes a newly added column actually appear on a database that
        predates it. Idempotent, and it never rewrites or drops a row.
        """
        for table, columns in EXPECTED_COLUMNS.items():
            present = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({table})")
            }
            if not present:
                # Table doesn't exist in this database; _init_schema owns it.
                continue
            for name, decl in columns.items():
                if name in present:
                    continue
                with self._conn:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                log.info("migrated %s: added column %s", table, name)

    # -- subscriptions ----------------------------------------------------

    def get_subscription(self, chat_id: int) -> Subscription | None:
        row = self._conn.execute(
            "SELECT chat_id, topics, time, enabled FROM subscriptions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return Subscription(
            chat_id=row["chat_id"],
            topics=json.loads(row["topics"]),
            time=row["time"],
            enabled=bool(row["enabled"]),
        )

    def save_subscription(self, sub: Subscription) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO subscriptions (chat_id, topics, time, enabled)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    topics = excluded.topics,
                    time = excluded.time,
                    enabled = excluded.enabled
                """,
                (sub.chat_id, json.dumps(sub.topics), sub.time, int(sub.enabled)),
            )

    def delete_subscription(self, chat_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))

    def list_subscriptions(self, enabled_only: bool = True) -> list:
        query = "SELECT chat_id, topics, time, enabled FROM subscriptions"
        if enabled_only:
            query += " WHERE enabled = 1"
        rows = self._conn.execute(query).fetchall()
        return [
            Subscription(
                chat_id=row["chat_id"],
                topics=json.loads(row["topics"]),
                time=row["time"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    # -- scores ------------------------------------------------------------

    def record_result(self, user_id: int, chat_id: int, correct: bool) -> dict:
        """Record one answered question; returns the updated score row."""
        row = self._conn.execute(
            "SELECT points, streak, correct, answered FROM scores "
            "WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        points = row["points"] if row else 0
        streak = row["streak"] if row else 0
        correct_n = row["correct"] if row else 0
        answered = row["answered"] if row else 0

        answered += 1
        if correct:
            points += BASE_POINTS + min(streak, MAX_STREAK_BONUS) * STREAK_BONUS
            streak += 1
            correct_n += 1
        else:
            streak = 0

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO scores (user_id, chat_id, points, streak, correct, answered)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    points = excluded.points,
                    streak = excluded.streak,
                    correct = excluded.correct,
                    answered = excluded.answered
                """,
                (user_id, chat_id, points, streak, correct_n, answered),
            )
        return {
            "points": points,
            "streak": streak,
            "correct": correct_n,
            "answered": answered,
        }

    def get_score(self, user_id: int, chat_id: int) -> dict:
        row = self._conn.execute(
            "SELECT points, streak, correct, answered FROM scores "
            "WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if row is None:
            return {"points": 0, "streak": 0, "correct": 0, "answered": 0}
        return dict(row)

    def leaderboard(self, chat_id: int, limit: int = 10) -> list:
        rows = self._conn.execute(
            "SELECT user_id, points, streak, correct, answered FROM scores "
            "WHERE chat_id = ? ORDER BY points DESC, correct DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
