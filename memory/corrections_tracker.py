"""
Corrections tracker — saves and queries grammatical corrections.
Provides analytics on error patterns to help the agent suggest study topics.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from config.settings import DB_PATH, RECENT_ERRORS_SESSIONS, MAX_ERRORS_INJECTED
from config.logging_config import setup_logging
from memory.database import DatabaseManager, get_db

logger = setup_logging()


class CorrectionsTracker:
    """
    Tracks all corrections made during sessions.
    Provides queries for error patterns, frequent mistakes, and progress metrics.
    """

    def __init__(self, db_path: str | None = None):
        self._db: DatabaseManager | None = None
        self._db_path = db_path or str(DB_PATH)
        self._current_session_id: int | None = None

    async def initialize(self):
        """Ensure DB connection is available."""
        self._db = await get_db()

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise RuntimeError(
                "CorrectionsTracker not initialized. Call initialize() first."
            )
        return self._db

    def set_session_id(self, session_id: int):
        """Set the current session ID for tracking."""
        self._current_session_id = session_id

    async def record_correction(
        self,
        original_text: str,
        corrected_text: str,
        error_type: str = "grammar",
        explanation: str = "",
        error_category: str = "",
        session_id: int | None = None,
    ) -> int:
        """
        Record a single correction in the database.

        Returns the correction ID.
        """
        sid = session_id or self._current_session_id

        correction_data = {
            "session_id": sid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_text": original_text[:500],  # Truncate to avoid huge rows
            "corrected_text": corrected_text[:500],
            "error_type": error_type,
            "explanation": explanation[:1000] if explanation else "",
            "error_category": error_category or self._infer_category(
                original_text, corrected_text, explanation
            ),
        }

        correction_id = await self.db.insert("corrections", correction_data)

        # Update session correction count
        if sid:
            await self.db.execute(
                "UPDATE sessions SET total_corrections = total_corrections + 1 WHERE id = ?",
                (sid,),
            )

        logger.debug(
            f"Recorded correction #{correction_id}: "
            f"'{original_text[:40]}' → '{corrected_text[:40]}'"
        )

        return correction_id

    async def get_session_corrections(self, session_id: int) -> list[dict]:
        """Get all corrections for a specific session."""
        return await self.db.fetch_all(
            "SELECT * FROM corrections WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        )

    async def get_frequent_errors(
        self,
        recent_sessions: int = RECENT_ERRORS_SESSIONS,
        limit: int = MAX_ERRORS_INJECTED,
        days: int = 30,
    ) -> list[tuple[str, int]]:
        """
        Get the most frequent error categories from recent sessions.

        Returns list of (category, count) tuples, ordered by frequency.
        """
        rows = await self.db.fetch_all(
            """
            SELECT error_category, COUNT(*) as count
            FROM corrections c
            JOIN sessions s ON c.session_id = s.id
            WHERE c.timestamp >= datetime('now', ?)
            GROUP BY error_category
            ORDER BY count DESC
            LIMIT ?
            """,
            (f"-{days} days", limit),
        )

        return [(row["error_category"], row["count"]) for row in rows]

    async def get_errors_this_session(self) -> list[dict]:
        """Get all errors from the current session."""
        if not self._current_session_id:
            return []

        return await self.db.fetch_all(
            """
            SELECT * FROM corrections
            WHERE session_id = ?
            ORDER BY timestamp DESC
            """,
            (self._current_session_id,),
        )

    async def get_recent_corrections_text(self, limit: int = 20) -> str:
        """
        Get recent corrections as a human-readable summary string.
        Used for injecting into the system prompt.
        """
        corrections = await self.db.fetch_all(
            """
            SELECT original_text, corrected_text, error_type, explanation, error_category
            FROM corrections
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )

        if not corrections:
            return "No recent corrections."

        by_category: dict[str, list[dict]] = {}
        for c in corrections:
            cat = c.get("error_category", c.get("error_type", "unknown"))
            by_category.setdefault(cat, []).append(c)

        lines = []
        for category, items in by_category.items():
            examples = [
                f"'{item['original_text'][:50]}' → '{item['corrected_text'][:50]}'"
                for item in items[:3]
            ]
            lines.append(f"  {category} ({len(items)} times): {', '.join(examples)}")

        return "Recent error patterns:\n" + "\n".join(lines)

    async def get_progress_stats(
        self, days: int = 7
    ) -> dict[str, int | float]:
        """
        Get progress statistics for a time period.

        Returns dict with:
        - total_corrections: Total corrections in period
        - unique_categories: Number of unique error categories
        - sessions_analyzed: Number of sessions with corrections
        - most_frequent_category: Category with most errors
        - avg_corrections_per_session: Average corrections per session
        """
        stats = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_corrections,
                COUNT(DISTINCT error_category) as unique_categories,
                COUNT(DISTINCT session_id) as sessions_analyzed
            FROM corrections
            WHERE timestamp >= datetime('now', ?)
            """,
            (f"-{days} days",),
        )

        most_frequent = await self.db.fetch_one(
            """
            SELECT error_category, COUNT(*) as count
            FROM corrections
            WHERE timestamp >= datetime('now', ?)
            GROUP BY error_category
            ORDER BY count DESC
            LIMIT 1
            """,
            (f"-{days} days",),
        )

        result = {
            "total_corrections": stats.get("total_corrections", 0) if stats else 0,
            "unique_categories": stats.get("unique_categories", 0) if stats else 0,
            "sessions_analyzed": stats.get("sessions_analyzed", 0) if stats else 0,
            "most_frequent_category": most_frequent["error_category"] if most_frequent and most_frequent["error_category"] else "none",
            "avg_corrections_per_session": 0,
        }

        if result["sessions_analyzed"] > 0 and stats:
            result["avg_corrections_per_session"] = round(
                result["total_corrections"] / result["sessions_analyzed"], 1
            )

        return result

    async def get_daily_history(
        self, days: int = 30
    ) -> list[dict[str, str | int]]:
        """Get correction counts per day for progress chart."""
        rows = await self.db.fetch_all(
            """
            SELECT date(timestamp) as day, COUNT(*) as count
            FROM corrections
            WHERE timestamp >= datetime('now', ?)
            GROUP BY date(timestamp)
            ORDER BY day
            """,
            (f"-{days} days",),
        )

        return [
            {"day": row["day"], "count": row["count"]}
            for row in rows
        ]

    async def has_repeated_errors(
        self,
        category: str,
        threshold: int = 3,
        recent_sessions: int = 3,
    ) -> bool:
        """
        Check if a specific error category has exceeded the threshold
        in recent sessions — triggers topic suggestions.
        """
        row = await self.db.fetch_one(
            """
            SELECT COUNT(*) as cnt FROM corrections
            WHERE error_category = ?
              AND session_id IN (
                  SELECT id FROM sessions
                  ORDER BY started_at DESC
                  LIMIT ?
              )
            """,
            (category, recent_sessions),
        )

        count = row["cnt"] if row else 0
        return count >= threshold

    async def get_corrections_for_export(self) -> list[dict]:
        """Get all corrections with session context for CSV export."""
        return await self.db.fetch_all(
            """
            SELECT
                c.id,
                c.timestamp,
                c.original_text,
                c.corrected_text,
                c.error_type,
                c.error_category,
                c.explanation,
                s.started_at as session_started
            FROM corrections c
            LEFT JOIN sessions s ON c.session_id = s.id
            ORDER BY c.timestamp DESC
            """
        )

    @staticmethod
    def _infer_category(
        original: str, corrected: str, explanation: str
    ) -> str:
        """Infer error category from correction details."""
        combined = f"{original} {corrected} {explanation}".lower()

        categories = {
            "tense": ["tense", "past", "present", "future", "perfect", "conjugat"],
            "preposition": ["preposition", " in ", " on ", " at ", " for ", " to "],
            "article": ["article", " a ", " an ", " the "],
            "word_order": ["word order", "order of words"],
            "subject_verb_agreement": ["subject-verb", "agreement"],
            "plural": ["plural", "singular", "countable"],
            "pronoun": ["pronoun", "possessive"],
            "modal": ["modal", "should", "could", "would"],
            "conditional": ["conditional", "if.*would"],
            "comparative": ["comparative", "superlative", "more.*than"],
        }

        for category, keywords in categories.items():
            for kw in keywords:
                if kw in combined:
                    return category

        return "grammar"
