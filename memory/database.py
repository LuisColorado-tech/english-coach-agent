"""
SQLite database initialization and connection management for ECA.
Uses aiosqlite for async operations. Creates tables on first run.
Manages schema migrations.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from config.settings import DB_PATH
from config.logging_config import setup_logging

logger = setup_logging()

# Current schema version for migration tracking
SCHEMA_VERSION = 1

# Table definitions
SCHEMA = {
    "schema_version": """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,

    "sessions": """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            duration_seconds INTEGER DEFAULT 0,
            total_corrections INTEGER DEFAULT 0,
            total_turns INTEGER DEFAULT 0,
            topics_covered TEXT,
            session_summary TEXT,
            triggered_by TEXT DEFAULT 'user'
        )
    """,

    "corrections": """
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES sessions(id),
            timestamp DATETIME NOT NULL,
            original_text TEXT NOT NULL,
            corrected_text TEXT NOT NULL,
            error_type TEXT NOT NULL DEFAULT 'grammar',
            explanation TEXT,
            error_category TEXT
        )
    """,

    "vocabulary": """
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES sessions(id),
            word_or_phrase TEXT NOT NULL,
            definition TEXT,
            example_sentence TEXT,
            introduced_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,

    "topic_suggestions": """
        CREATE TABLE IF NOT EXISTS topic_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic TEXT NOT NULL,
            reason TEXT,
            error_category_reference TEXT,
            reviewed INTEGER DEFAULT 0
        )
    """,

    "spontaneous_events": """
        CREATE TABLE IF NOT EXISTS spontaneous_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic_used TEXT,
            user_responded INTEGER DEFAULT 0,
            session_id INTEGER REFERENCES sessions(id)
        )
    """,

    # Indexes for common queries
    "idx_corrections_session": """
        CREATE INDEX IF NOT EXISTS idx_corrections_session
        ON corrections(session_id)
    """,
    "idx_corrections_category": """
        CREATE INDEX IF NOT EXISTS idx_corrections_category
        ON corrections(error_category)
    """,
    "idx_corrections_timestamp": """
        CREATE INDEX IF NOT EXISTS idx_corrections_timestamp
        ON corrections(timestamp)
    """,
    "idx_sessions_started": """
        CREATE INDEX IF NOT EXISTS idx_sessions_started
        ON sessions(started_at)
    """,
    "idx_vocabulary_session": """
        CREATE INDEX IF NOT EXISTS idx_vocabulary_session
        ON vocabulary(session_id)
    """,
}


class DatabaseManager:
    """
    Manages SQLite database lifecycle.
    Handles connection pooling, table creation, and migrations.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DB_PATH)
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Create database and tables if they don't exist."""
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrent access
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")

        # Create all tables
        for name, ddl in SCHEMA.items():
            await self._connection.execute(ddl)

        # Check/apply migrations
        await self._migrate()

        await self._connection.commit()

        logger.info(f"Database initialized at {self.db_path}")

    async def _migrate(self):
        """Apply any pending schema migrations."""
        cursor = await self._connection.execute(
            "SELECT MAX(version) FROM schema_version"
        )
        row = await cursor.fetchone()
        current_version = row[0] if row and row[0] else 0

        if current_version < SCHEMA_VERSION:
            # Record new version
            await self._connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            logger.info(
                f"Database migrated: v{current_version} → v{SCHEMA_VERSION}"
            )

    async def get_connection(self) -> aiosqlite.Connection:
        """Get the current database connection."""
        if self._connection is None:
            await self.initialize()
        return self._connection

    async def execute(self, sql: str, params: tuple | None = None) -> aiosqlite.Cursor:
        """Execute a SQL query. Returns cursor for iteration."""
        conn = await self.get_connection()
        async with self._lock:
            cursor = await conn.execute(sql, params or ())
            await conn.commit()
            return cursor

    async def fetch_all(self, sql: str, params: tuple | None = None) -> list[dict]:
        """Execute a SELECT query and return all rows as dicts."""
        conn = await self.get_connection()
        conn.row_factory = aiosqlite.Row
        async with self._lock:
            cursor = await conn.execute(sql, params or ())
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: tuple | None = None) -> dict | None:
        """Execute a SELECT query and return the first row as dict."""
        conn = await self.get_connection()
        conn.row_factory = aiosqlite.Row
        async with self._lock:
            cursor = await conn.execute(sql, params or ())
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def insert(self, table: str, data: dict) -> int:
        """Insert a row and return the new ID."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = tuple(data.values())

        conn = await self.get_connection()
        async with self._lock:
            cursor = await conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                values,
            )
            await conn.commit()
            return cursor.lastrowid

    async def execute_many(self, sql: str, params_list: list[tuple]):
        """Execute a SQL statement with multiple parameter sets."""
        conn = await self.get_connection()
        async with self._lock:
            await conn.executemany(sql, params_list)
            await conn.commit()

    async def close(self):
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.debug("Database connection closed")

    # === Convenience queries ===

    async def get_session_count(self) -> int:
        """Return total number of sessions."""
        row = await self.fetch_one("SELECT COUNT(*) as cnt FROM sessions")
        return row["cnt"] if row else 0

    async def get_total_corrections(self) -> int:
        """Return total number of corrections across all sessions."""
        row = await self.fetch_one("SELECT COUNT(*) as cnt FROM corrections")
        return row["cnt"] if row else 0

    async def get_corrections_by_category(self, days: int = 7) -> list[dict]:
        """Get correction counts by category for recent sessions."""
        return await self.fetch_all(
            """
            SELECT error_category, COUNT(*) as count
            FROM corrections
            WHERE timestamp >= datetime('now', ?)
            GROUP BY error_category
            ORDER BY count DESC
            """,
            (f"-{days} days",),
        )

    async def get_vocabulary_count(self) -> int:
        """Return total vocabulary entries."""
        row = await self.fetch_one("SELECT COUNT(*) as cnt FROM vocabulary")
        return row["cnt"] if row else 0


# Singleton instance
_db_manager: DatabaseManager | None = None


async def get_db() -> DatabaseManager:
    """Get or create the singleton database manager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        await _db_manager.initialize()
    return _db_manager


async def close_db():
    """Close the singleton database connection."""
    global _db_manager
    if _db_manager:
        await _db_manager.close()
        _db_manager = None
