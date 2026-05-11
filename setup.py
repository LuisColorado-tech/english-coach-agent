#!/usr/bin/env python3
"""
English Coach Agent - Setup script for Windows
Installs dependencies, downloads models, and runs the setup wizard.
"""

import subprocess
import sys
import os
from pathlib import Path


MIN_PYTHON = (3, 11)

PROJECT_ROOT = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_ROOT / "venv"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


def check_python_version():
    if sys.version_info < MIN_PYTHON:
        print(f"ERROR: Python {'.'.join(map(str, MIN_PYTHON))}+ required. "
              f"Current: {sys.version}")
        sys.exit(1)
    print(f"[OK] Python {sys.version}")


def create_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / ".gitkeep").touch(exist_ok=True)
    print("[OK] Directories created")


def install_dependencies():
    print("[INFO] Installing Python dependencies...")
    req_file = PROJECT_ROOT / "requirements.txt"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Try pipwin for pyaudio on Windows if needed
    if sys.platform == "win32":
        try:
            import pyaudio
        except ImportError:
            print("[INFO] pyaudio not found. Trying pipwin fallback...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "pipwin"],
                stdout=sys.stdout, stderr=sys.stderr,
            )
            subprocess.check_call(
                [sys.executable, "-m", "pipwin", "install", "pyaudio"],
                stdout=sys.stdout, stderr=sys.stderr,
            )

    print("[OK] Dependencies installed")


def download_models():
    print("[INFO] Downloading faster-whisper model...")
    from faster_whisper import download_model
    model_size = os.environ.get("ECA_WHISPER_MODEL", "base.en")
    download_model(model_size)
    print(f"[OK] Whisper model '{model_size}' downloaded")

    print("[INFO] Silero VAD model will be downloaded on first use (~30MB)")


def setup_env_file():
    env_example = PROJECT_ROOT / ".env.example"
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print("[INFO] Creating .env from template...")
        env_file.write_text(env_example.read_text())
        print("[INFO] Edit .env and set your DEEPSEEK_API_KEY")
    else:
        print("[INFO] .env already exists, skipping")


def run_setup_wizard():
    print("\n=== English Coach Agent Setup ===\n")
    print("Launching setup wizard...\n")
    # Imported here to avoid dependency checks before install
    try:
        from ui.setup_wizard import SetupWizard
        import customtkinter as ctk

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        root = ctk.CTk()
        wizard = SetupWizard(root)
        root.mainloop()
    except ImportError as e:
        print(f"[WARN] Could not launch UI wizard: {e}")
        _cli_setup_fallback()


def _cli_setup_fallback():
    """Fallback CLI setup if GUI fails."""
    profile_path = DATA_DIR / "profile.json"
    if profile_path.exists():
        print("[INFO] Profile already exists, skipping CLI setup")
        return

    import json
    from datetime import datetime, timezone

    print("\n--- CLI Setup (fallback) ---")
    name = input("Your preferred name: ").strip() or "User"
    level = input("English level (beginner/intermediate/upper_intermediate/advanced): ").strip() or "intermediate"
    role = input("Your professional role: ").strip() or "Professional"
    company = input("Company: ").strip() or ""
    interests = input("Topics of interest (comma-separated): ").strip() or "technology"

    profile = {
        "user": {
            "name": name,
            "native_language": "Spanish",
            "location": "",
            "timezone": "America/Bogota",
        },
        "english_profile": {
            "current_level": level,
            "learning_goal": "Improve conversational fluency",
            "preferred_accent": "american",
            "topics_of_interest": [t.strip() for t in interests.split(",")],
            "topics_to_avoid": [],
        },
        "professional_profile": {
            "role": role,
            "company": company,
            "industry": "",
            "skills": [],
            "current_projects": [],
        },
        "personal_profile": {
            "hobbies": [],
            "personality_notes": "",
            "communication_style": "",
        },
        "agent_config": {
            "correction_style": "gentle",
            "spontaneous_triggers_enabled": True,
            "spontaneous_interval_minutes": 60,
            "daily_checkin_time": "09:00",
            "tts_voice": os.environ.get("ECA_TTS_VOICE", "en-US-AriaNeural"),
            "ui_always_on_top": True,
        },
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "profile_version": "1.0.0",
        },
    }

    profile_path.write_text(json.dumps(profile, indent=2))
    print(f"[OK] Profile saved to {profile_path}")


def main():
    print("English Coach Agent - Setup\n")
    check_python_version()
    create_directories()
    install_dependencies()
    download_models()
    setup_env_file()
    run_setup_wizard()

    print("\n=== Setup Complete! ===")
    print(f"\nRun the agent with: cd {PROJECT_ROOT} && python run.py")
    print("Or double-click run.bat on Windows.\n")


if __name__ == "__main__":
    main()
