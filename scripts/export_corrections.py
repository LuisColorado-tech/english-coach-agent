#!/usr/bin/env python3
"""
Export corrections history to CSV for analysis.
"""

import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging_config import setup_logging
from memory.database import get_db, close_db

logger = setup_logging()


async def export_to_csv(output_path: str | None = None, days: int = 30):
    db = await get_db()

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"corrections_export_{timestamp}.csv"

    corrections = await db.fetch_all(
        """
        SELECT c.id, c.timestamp, c.original_text, c.corrected_text,
               c.error_type, c.error_category, c.explanation,
               s.started_at as session_started, s.triggered_by
        FROM corrections c
        LEFT JOIN sessions s ON c.session_id = s.id
        WHERE c.timestamp >= datetime('now', ?)
        ORDER BY c.timestamp DESC
        """,
        (f"-{days} days",),
    )

    if not corrections:
        print(f"No corrections found in the last {days} days.")
        await close_db()
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=corrections[0].keys())
        writer.writeheader()
        writer.writerows(corrections)

    print(f"Exported {len(corrections)} corrections to: {output_path}")
    await close_db()


async def export_vocabulary(output_path: str | None = None):
    db = await get_db()
    if output_path is None:
        output_path = f"vocabulary_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    words = await db.fetch_all(
        "SELECT v.*, s.started_at FROM vocabulary v LEFT JOIN sessions s ON v.session_id = s.id ORDER BY v.introduced_at DESC"
    )
    if not words:
        print("No vocabulary entries found.")
        await close_db()
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=words[0].keys())
        writer.writeheader()
        writer.writerows(words)

    print(f"Exported {len(words)} vocabulary entries to: {output_path}")
    await close_db()


async def export_sessions(output_path: str | None = None):
    db = await get_db()
    if output_path is None:
        output_path = f"sessions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    sessions = await db.fetch_all(
        "SELECT id, started_at, ended_at, duration_seconds, total_corrections, total_turns, triggered_by FROM sessions ORDER BY started_at DESC"
    )
    if not sessions:
        print("No sessions found.")
        await close_db()
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sessions[0].keys())
        writer.writeheader()
        writer.writerows(sessions)

    print(f"Exported {len(sessions)} sessions to: {output_path}")
    await close_db()


def run_export():
    import argparse
    parser = argparse.ArgumentParser(description="Export ECA data to CSV")
    parser.add_argument("type", nargs="?", choices=["corrections", "vocabulary", "sessions", "all"], default="corrections")
    parser.add_argument("--output", "-o", type=str)
    parser.add_argument("--days", "-d", type=int, default=30)
    args = parser.parse_args()

    if args.type in ("corrections", "all"):
        asyncio.run(export_to_csv(args.output, args.days))
    if args.type in ("vocabulary", "all"):
        asyncio.run(export_vocabulary(args.output))
    if args.type in ("sessions", "all"):
        asyncio.run(export_sessions(args.output))


if __name__ == "__main__":
    run_export()
