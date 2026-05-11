#!/usr/bin/env python3
"""Resets the user profile to defaults. Keeps a backup by default."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.profile_manager import ProfileManager
from config.logging_config import setup_logging

logger = setup_logging()


def reset_profile(keep_backup: bool = True):
    pm = ProfileManager()

    if not pm.exists():
        print("No profile found. Nothing to reset.")
        return

    print(f"Current profile:\n{pm.get_summary()}")
    print()

    confirm = input("Reset profile to defaults? This keeps a backup. [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    pm.reset(keep_backup=keep_backup)
    print("Profile reset to defaults.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reset ECA user profile")
    parser.add_argument("--force", action="store_true", help="Reset without confirmation")
    parser.add_argument("--no-backup", action="store_true", help="Don't keep a backup")

    args = parser.parse_args()

    if args.force:
        pm = ProfileManager()
        pm.reset(keep_backup=not args.no_backup)
        print("Profile reset to defaults.")
    else:
        reset_profile(keep_backup=not args.no_backup)
