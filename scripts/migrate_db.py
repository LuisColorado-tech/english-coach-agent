#!/usr/bin/env python3
"""Database migration utility for the English Coach Agent."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging_config import setup_logging
from memory.database import get_db, close_db, SCHEMA_VERSION

logger = setup_logging()


async def check_migrations():
    db = await get_db()
    cursor = await db.execute("SELECT MAX(version) FROM schema_version")
    row = await cursor.fetchone()
    current = row[0] if row and row[0] else 0

    print(f"Database version: {current}")
    print(f"Latest schema: {SCHEMA_VERSION}")

    if current < SCHEMA_VERSION:
        print(f"Migration needed: v{current} → v{SCHEMA_VERSION}")
        print("Run: python scripts/migrate_db.py --apply")
    else:
        print("Database is up to date.")

    await close_db()


async def apply_migrations():
    db = await get_db()
    cursor = await db.execute("SELECT MAX(version) FROM schema_version")
    row = await cursor.fetchone()
    current = row[0] if row and row[0] else 0

    if current >= SCHEMA_VERSION:
        print("Database already up to date.")
        await close_db()
        return

    await db.execute(
        "INSERT INTO schema_version (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )
    print(f"Migration applied: v{current} → v{SCHEMA_VERSION}")
    await close_db()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manage ECA database migrations")
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations")
    parser.add_argument("--check", action="store_true", help="Check migration status")
    args = parser.parse_args()

    if args.apply:
        asyncio.run(apply_migrations())
    else:
        asyncio.run(check_migrations())
