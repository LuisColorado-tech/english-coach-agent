"""
Session manager — creates, updates, and queries conversation sessions.
Manages session lifecycle and provides session-level statistics.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from config.settings import DB_PATH
from config.logging_config import setup_logging
from memory.database import DatabaseManager, get_db

logger = setup_logging()


class SessionManager:
    """
    Manages conversation session lifecycle.
    Each session represents a continuous period of practice.
    """

    def __init__(self, db_path: str | None = None):
        self._db: DatabaseManager | None = None
        self._db_path = db_path or str(DB_PATH)
        self._active_session_id: int | None = None
        self._session_start_time: datetime | None = None

    async def initialize(self):
        """Ensure DB connection is available."""
        self._db = await get_db()

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise RuntimeError(
                "SessionManager not initialized. Call initialize() first."
            )
        return self._db

    @property
    def active_session_id(self) -> int | None:
        return self._active_session_id

    @property
    def is_session_active(self) -> bool:
        return self._active_session_id is not None

    async def start_session(
        self, triggered_by: str = "user"
    ) -> int:
        """
        Start a new practice session.

        Args:
            triggered_by: 'user' for user-initiated, 'spontaneous' for agent-initiated,
                         'scheduler' for scheduled triggers

        Returns:
            The new session ID
        """
        if self.is_session_active:
            logger.warning("A session is already active. Ending it first.")
            await self.end_session()

        self._session_start_time = datetime.now(timezone.utc)

        session_data = {
            "started_at": self._session_start_time.isoformat(),
            "triggered_by": triggered_by,
            "total_corrections": 0,
            "total_turns": 0,
            "topics_covered": json.dumps([]),
            "session_summary": "",
        }

        self._active_session_id = await self.db.insert("sessions", session_data)

        logger.info(
            f"Session #{self._active_session_id} started "
            f"(triggered by: {triggered_by})"
        )

        return self._active_session_id

    async def end_session(self, summary: str = "") -> dict | None:
        """
        End the current session.

        Args:
            summary: Optional LLM-generated summary of the session

        Returns:
            Session dict with final stats, or None if no session was active
        """
        if not self._active_session_id:
            return None

        end_time = datetime.now(timezone.utc)
        duration = int(
            (end_time - self._session_start_time).total_seconds()
        ) if self._session_start_time else 0

        await self.db.execute(
            """
            UPDATE sessions
            SET ended_at = ?,
                duration_seconds = ?,
                session_summary = ?
            WHERE id = ?
            """,
            (end_time.isoformat(), duration, summary or "", self._active_session_id),
        )

        # Get final stats
        session = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE id = ?",
            (self._active_session_id,),
        )

        logger.info(
            f"Session #{self._active_session_id} ended "
            f"(duration: {duration}s, corrections: {session.get('total_corrections', 0) if session else 0})"
        )

        sid = self._active_session_id
        self._active_session_id = None
        self._session_start_time = None

        return session

    async def record_turn(self):
        """Increment turn counter for the current session."""
        if self._active_session_id:
            await self.db.execute(
                "UPDATE sessions SET total_turns = total_turns + 1 WHERE id = ?",
                (self._active_session_id,),
            )

    async def add_topic(self, topic: str):
        """Add a topic to the current session's topics_covered."""
        if not self._active_session_id:
            return

        row = await self.db.fetch_one(
            "SELECT topics_covered FROM sessions WHERE id = ?",
            (self._active_session_id,),
        )

        if row:
            try:
                topics = json.loads(row.get("topics_covered", "[]"))
            except (json.JSONDecodeError, TypeError):
                topics = []

            if topic not in topics:
                topics.append(topic)

                # Keep only last 20 topics
                if len(topics) > 20:
                    topics = topics[-20:]

                await self.db.execute(
                    "UPDATE sessions SET topics_covered = ? WHERE id = ?",
                    (json.dumps(topics), self._active_session_id),
                )

    async def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        """Get the most recent sessions."""
        return await self.db.fetch_all(
            """
            SELECT * FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def get_session_summary(self, session_id: int | None = None) -> dict:
        """Get a summary of a specific session or the current one."""
        sid = session_id or self._active_session_id
        if not sid:
            return {}

        session = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE id = ?",
            (sid,),
        )

        if not session:
            return {}

        # Get corrections for this session
        corrections = await self.db.fetch_all(
            """
            SELECT error_type, error_category, original_text, corrected_text
            FROM corrections
            WHERE session_id = ?
            """,
            (sid,),
        )

        # Get vocabulary for this session
        vocabulary = await self.db.fetch_all(
            """
            SELECT word_or_phrase, definition
            FROM vocabulary
            WHERE session_id = ?
            """,
            (sid,),
        )

        return {
            "session": session,
            "corrections": corrections,
            "vocabulary": vocabulary,
            "correction_count": len(corrections),
            "vocabulary_count": len(vocabulary),
        }

    async def get_streak_days(self) -> int:
        """
        Calculate the current streak of consecutive practice days.
        A day counts if there was at least one session on that day.
        """
        rows = await self.db.fetch_all(
            """
            SELECT DISTINCT date(started_at) as practice_date
            FROM sessions
            ORDER BY practice_date DESC
            """
        )

        if not rows:
            return 0

        today = datetime.now(timezone.utc).date()
        streak = 0

        for i, row in enumerate(rows):
            practice_date = datetime.fromisoformat(row["practice_date"]).date()
            expected_date = today - timedelta(days=i)

            if practice_date == expected_date:
                streak += 1
            elif practice_date < expected_date:
                break  # Gap found

        return streak

    async def get_weekly_stats(self) -> dict:
        """Get aggregate stats for the current week."""
        rows = await self.db.fetch_all(
            """
            SELECT
                COUNT(*) as session_count,
                COALESCE(SUM(total_turns), 0) as total_turns,
                COALESCE(SUM(total_corrections), 0) as total_corrections,
                COALESCE(SUM(duration_seconds), 0) as total_seconds
            FROM sessions
            WHERE started_at >= datetime('now', '-7 days')
            """
        )

        if not rows or not rows[0]:
            return {
                "session_count": 0,
                "total_turns": 0,
                "total_corrections": 0,
                "total_minutes": 0,
            }

        row = rows[0]
        return {
            "session_count": row["session_count"] or 0,
            "total_turns": row["total_turns"] or 0,
            "total_corrections": row["total_corrections"] or 0,
            "total_minutes": round((row["total_seconds"] or 0) / 60),
        }

    async def get_total_stats(self) -> dict:
        """Get lifetime aggregate stats."""
        row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_sessions,
                COALESCE(SUM(duration_seconds), 0) as total_seconds,
                COALESCE(SUM(total_corrections), 0) as total_corrections,
                COALESCE(AVG(duration_seconds), 0) as avg_duration
            FROM sessions
            """
        )

        if not row:
            return {
                "total_sessions": 0,
                "total_hours": 0,
                "total_corrections": 0,
                "avg_session_minutes": 0,
            }

        return {
            "total_sessions": row["total_sessions"] or 0,
            "total_hours": round((row["total_seconds"] or 0) / 3600, 1),
            "total_corrections": row["total_corrections"] or 0,
            "avg_session_minutes": round(
                (row["avg_duration"] or 0) / 60, 1
            ),
        }
