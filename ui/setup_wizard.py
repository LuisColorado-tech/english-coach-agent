"""
Setup wizard for the English Coach Agent — first-run configuration.
Guides the user through profile setup with a multi-step UI.
Uses customtkinter for modern Windows look.
"""

import asyncio
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import PROFILE_PATH, DEEPSEEK_API_KEY
from config.logging_config import setup_logging

logger = setup_logging()


class SetupWizard:
    """
    Multi-step setup wizard for first-run configuration.
    Guides user through: name, level, profession, interests, voice, style, API key.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("English Coach Agent — Setup")
        self.root.geometry("700x550")
        self.root.resizable(False, False)

        # Center on screen
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - 700) // 2
        y = (screen_h - 550) // 2
        self.root.geometry(f"+{x}+{y}")

        # Data collected through wizard
        self.data = {
            "user": {
                "name": "",
                "native_language": "Spanish",
                "location": "",
                "timezone": "America/Bogota",
            },
            "english_profile": {
                "current_level": "intermediate",
                "learning_goal": "Improve conversational fluency",
                "preferred_accent": "american",
                "topics_of_interest": [],
                "topics_to_avoid": [],
            },
            "professional_profile": {
                "role": "",
                "company": "",
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
                "tts_voice": "en-US-AriaNeural",
                "ui_always_on_top": True,
            },
            "meta": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "profile_version": "1.0.0",
            },
        }

        self._steps = []
        self._current_step = 0
        self._widgets = {}
        self._create_steps()

        # Navigation buttons (created once, reused)
        self._nav_frame = None
        self._back_btn = None
        self._next_btn = None
        self._finish_btn = None
        self._create_navigation()

        # Show first step
        self._show_step(0)

    def _create_steps(self):
        """Define all wizard steps."""
        self._steps = [
            {
                "title": "Welcome!",
                "content": self._step_welcome,
            },
            {
                "title": "About You",
                "content": self._step_about_you,
            },
            {
                "title": "English Level",
                "content": self._step_english_level,
            },
            {
                "title": "Your Profession",
                "content": self._step_profession,
            },
            {
                "title": "Your Interests",
                "content": self._step_interests,
            },
            {
                "title": "Voice & Style",
                "content": self._step_voice_style,
            },
            {
                "title": "API Key",
                "content": self._step_api_key,
            },
        ]

    def _create_navigation(self):
        """Create the navigation button bar at the bottom."""
        import customtkinter as ctk

        self._nav_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self._nav_frame.pack(side="bottom", fill="x", padx=30, pady=20)

        self._back_btn = ctk.CTkButton(
            self._nav_frame,
            text=" Back",
            width=100,
            command=self._go_back,
            fg_color="gray40",
        )

        self._next_btn = ctk.CTkButton(
            self._nav_frame,
            text="Next ",
            width=100,
            command=self._go_next,
        )

    def _show_step(self, index: int):
        """Display a specific wizard step."""
        import customtkinter as ctk

        # Clear previous step content
        for widget in self._widgets.values():
            widget.pack_forget()

        self._widgets.clear()
        self._current_step = index
        step = self._steps[index]

        # Update navigation
        self._back_btn.pack_forget()
        self._next_btn.pack_forget()
        if hasattr(self, '_finish_btn') and self._finish_btn:
            self._finish_btn.pack_forget()

        if index > 0:
            self._back_btn.pack(side="left", padx=(0, 10))

        if index < len(self._steps) - 1:
            self._next_btn.pack(side="right", padx=(10, 0))
        else:
            self._finish_btn = ctk.CTkButton(
                self._nav_frame,
                text="Finish Setup",
                width=120,
                command=self._finish,
                fg_color="#2E8B57",
            )
            self._finish_btn.pack(side="right", padx=(10, 0))

        # Render step content
        content_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=40, pady=(30, 10))
        self._widgets["content_frame"] = content_frame

        step["content"](content_frame)

    def _go_next(self):
        if self._current_step < len(self._steps) - 1:
            self._show_step(self._current_step + 1)

    def _go_back(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _finish(self):
        """Save profile and close wizard."""
        try:
            from memory.profile_manager import ProfileManager

            pm = ProfileManager()
            success = pm.update_entire_profile(self.data)

            if success:
                logger.info("Profile saved from setup wizard")
                self._show_completion()
            else:
                logger.error("Failed to save profile from wizard")
        except Exception as e:
            logger.error(f"Error saving profile: {e}")

    def _show_completion(self):
        """Show completion screen."""
        import customtkinter as ctk

        for widget in self._widgets.values():
            widget.pack_forget()
        self._widgets.clear()

        if hasattr(self, '_finish_btn'):
            self._finish_btn.pack_forget()
        self._back_btn.pack_forget()
        self._next_btn.pack_forget()

        frame = ctk.CTkFrame(self.root, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=40, pady=30)
        self._widgets["frame"] = frame

        ctk.CTkLabel(
            frame,
            text="All Set!",
            font=("Segoe UI", 28, "bold"),
            text_color="#2E8B57",
        ).pack(pady=(40, 10))

        ctk.CTkLabel(
            frame,
            text=f"Your English coach is ready, {self.data['user']['name']}!",
            font=("Segoe UI", 16),
            wraplength=500,
        ).pack(pady=(0, 20))

        ctk.CTkLabel(
            frame,
            text="Run the agent with: python run.py\nor double-click run.bat",
            font=("Segoe UI", 13),
            text_color="gray70",
        ).pack(pady=(0, 30))

        ctk.CTkButton(
            frame,
            text="Start Agent Now",
            width=200,
            height=40,
            font=("Segoe UI", 14, "bold"),
            command=self.root.destroy,
        ).pack(pady=(10, 10))

    # === Step renderers ===

    def _step_welcome(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent,
            text="Welcome to Your English Coach",
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            parent,
            text=(
                "This setup wizard will help configure your personal\n"
                "English conversation coach. This will only take a minute."
            ),
            font=("Segoe UI", 14),
            wraplength=500,
            justify="center",
        ).pack(pady=(0, 30))

        features = [
            ("", "Practice English conversation anytime"),
            ("", "Get real-time grammar corrections"),
            ("", "Personalized to your level and interests"),
            ("", "Runs quietly in the background"),
        ]

        for icon, text in features:
            ctk.CTkLabel(
                parent,
                text=f"{icon} {text}",
                font=("Segoe UI", 13),
                text_color="gray80",
            ).pack(anchor="w", padx=80, pady=3)

    def _step_about_you(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="About You", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 20))

        ctk.CTkLabel(
            parent, text="What should I call you?", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        name_entry = ctk.CTkEntry(parent, width=350, height=35, placeholder_text="Your preferred name")
        name_entry.pack(pady=(5, 15))
        name_entry.insert(0, self.data["user"]["name"])
        self._widgets["name_entry"] = name_entry

        ctk.CTkLabel(
            parent, text="Where are you from? (city, country)", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        loc_entry = ctk.CTkEntry(parent, width=350, height=35, placeholder_text="e.g. Medellin, Colombia")
        loc_entry.pack(pady=(5, 15))
        loc_entry.insert(0, self.data["user"]["location"])
        self._widgets["loc_entry"] = loc_entry

        ctk.CTkLabel(
            parent, text="Native language", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        lang_combo = ctk.CTkComboBox(
            parent, width=350, height=35,
            values=["Spanish", "Portuguese", "French", "Italian", "German", "Other"],
        )
        lang_combo.set(self.data["user"]["native_language"])
        lang_combo.pack(pady=(5, 15))
        self._widgets["lang_combo"] = lang_combo

        # Save data when leaving step
        self._on_leave_step = self._save_about_you

    def _save_about_you(self):
        self.data["user"]["name"] = self._widgets.get("name_entry", None)
        if hasattr(self._widgets["name_entry"], "get"):
            self.data["user"]["name"] = self._widgets["name_entry"].get().strip() or "there"
        if "loc_entry" in self._widgets:
            self.data["user"]["location"] = self._widgets["loc_entry"].get().strip()
        if "lang_combo" in self._widgets:
            self.data["user"]["native_language"] = self._widgets["lang_combo"].get()

    def _step_english_level(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="Your English Level", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 20))

        levels = [
            ("beginner", "I know basic words and phrases"),
            ("intermediate", "I can hold simple conversations"),
            ("upper_intermediate", "I can discuss most topics comfortably"),
            ("advanced", "I'm fluent but want to refine details"),
        ]

        self._widgets["level_var"] = ctk.StringVar(value=self.data["english_profile"]["current_level"])

        for value, desc in levels:
            ctk.CTkRadioButton(
                parent,
                text=f"{desc}",
                variable=self._widgets["level_var"],
                value=value,
                font=("Segoe UI", 13),
            ).pack(anchor="w", padx=50, pady=4)

        ctk.CTkLabel(
            parent,
            text="\nWhat accent do you prefer?",
            font=("Segoe UI", 13),
        ).pack(anchor="w", padx=30)

        self._widgets["accent_var"] = ctk.StringVar(value=self.data["english_profile"]["preferred_accent"])

        accents_frame = ctk.CTkFrame(parent, fg_color="transparent")
        accents_frame.pack(fill="x", padx=30, pady=5)

        for value, label in [("american", "American"), ("british", "British"), ("australian", "Australian")]:
            ctk.CTkRadioButton(
                accents_frame,
                text=label,
                variable=self._widgets["accent_var"],
                value=value,
                font=("Segoe UI", 12),
            ).pack(side="left", padx=(0, 20))

        self._on_leave_step = self._save_english_level

    def _save_english_level(self):
        if "level_var" in self._widgets:
            self.data["english_profile"]["current_level"] = self._widgets["level_var"].get()
        if "accent_var" in self._widgets:
            self.data["english_profile"]["preferred_accent"] = self._widgets["accent_var"].get()

    def _step_profession(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="Your Profession", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 15))

        ctk.CTkLabel(
            parent, text="This helps me use relevant examples during practice.",
            font=("Segoe UI", 13), text_color="gray70"
        ).pack(pady=(0, 15))

        ctk.CTkLabel(
            parent, text="What is your role?", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        role_entry = ctk.CTkEntry(parent, width=350, height=35, placeholder_text="e.g. Software Developer")
        role_entry.pack(pady=(5, 10))
        role_entry.insert(0, self.data["professional_profile"]["role"])
        self._widgets["role_entry"] = role_entry

        ctk.CTkLabel(
            parent, text="Company (optional)", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        company_entry = ctk.CTkEntry(parent, width=350, height=35, placeholder_text="e.g. Acme Corp")
        company_entry.pack(pady=(5, 10))
        company_entry.insert(0, self.data["professional_profile"]["company"])
        self._widgets["company_entry"] = company_entry

        ctk.CTkLabel(
            parent, text="Key skills (comma-separated)", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        skills_entry = ctk.CTkEntry(parent, width=350, height=35, placeholder_text="e.g. Python, React, SQL")
        skills_entry.pack(pady=(5, 10))
        skills_entry.insert(0, ", ".join(self.data["professional_profile"]["skills"]))
        self._widgets["skills_entry"] = skills_entry

        self._on_leave_step = self._save_profession

    def _save_profession(self):
        self.data["professional_profile"]["role"] = (
            self._widgets["role_entry"].get().strip()
        )
        self.data["professional_profile"]["company"] = (
            self._widgets["company_entry"].get().strip()
        )
        skills_raw = self._widgets["skills_entry"].get().strip()
        self.data["professional_profile"]["skills"] = (
            [s.strip() for s in skills_raw.split(",") if s.strip()]
            if skills_raw else []
        )

    def _step_interests(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="Your Interests", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            parent, text="What topics do you enjoy talking about?",
            font=("Segoe UI", 13), text_color="gray70"
        ).pack(pady=(0, 15))

        ctk.CTkLabel(
            parent, text="Topics you like (comma-separated)", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        interests_entry = ctk.CTkEntry(
            parent, width=350, height=35,
            placeholder_text="e.g. technology, travel, sports, music"
        )
        interests_entry.pack(pady=(5, 15))
        interests_entry.insert(0, ", ".join(self.data["english_profile"]["topics_of_interest"]))
        self._widgets["interests_entry"] = interests_entry

        ctk.CTkLabel(
            parent, text="Topics to avoid (optional)", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        avoid_entry = ctk.CTkEntry(
            parent, width=350, height=35,
            placeholder_text="e.g. politics, religion"
        )
        avoid_entry.pack(pady=(5, 15))
        avoid_entry.insert(0, ", ".join(self.data["english_profile"]["topics_to_avoid"]))
        self._widgets["avoid_entry"] = avoid_entry

        self._on_leave_step = self._save_interests

    def _save_interests(self):
        interests_raw = self._widgets["interests_entry"].get().strip()
        self.data["english_profile"]["topics_of_interest"] = (
            [t.strip() for t in interests_raw.split(",") if t.strip()]
            if interests_raw else ["technology"]
        )
        avoid_raw = self._widgets["avoid_entry"].get().strip()
        self.data["english_profile"]["topics_to_avoid"] = (
            [t.strip() for t in avoid_raw.split(",") if t.strip()]
            if avoid_raw else []
        )

    def _step_voice_style(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="Voice & Correction Style", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 20))

        ctk.CTkLabel(
            parent, text="Choose your coach's voice:", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        self._widgets["voice_var"] = ctk.StringVar(value=self.data["agent_config"]["tts_voice"])

        voices = [
            ("en-US-AriaNeural", "Aria — Warm, clear (American female)"),
            ("en-US-GuyNeural", "Guy — Friendly, natural (American male)"),
            ("en-GB-SoniaNeural", "Sonia — Refined, polite (British female)"),
            ("en-AU-NatashaNeural", "Natasha — Cheerful (Australian female)"),
        ]

        for value, label in voices:
            ctk.CTkRadioButton(
                parent,
                text=label,
                variable=self._widgets["voice_var"],
                value=value,
                font=("Segoe UI", 12),
            ).pack(anchor="w", padx=50, pady=2)

        ctk.CTkLabel(
            parent, text="\nHow should I correct your mistakes?", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30, pady=(20, 5))

        self._widgets["style_var"] = ctk.StringVar(value=self.data["agent_config"]["correction_style"])

        styles = [
            ("immediate", "Immediately — correct inline as you speak"),
            ("gentle", "Gently — acknowledge first, then suggest (recommended)"),
            ("end_of_sentence", "At the end — wait until you finish, then correct"),
        ]

        for value, label in styles:
            ctk.CTkRadioButton(
                parent,
                text=label,
                variable=self._widgets["style_var"],
                value=value,
                font=("Segoe UI", 12),
            ).pack(anchor="w", padx=50, pady=2)

        self._on_leave_step = self._save_voice_style

    def _save_voice_style(self):
        self.data["agent_config"]["tts_voice"] = self._widgets["voice_var"].get()
        self.data["agent_config"]["correction_style"] = self._widgets["style_var"].get()

    def _step_api_key(self, parent):
        import customtkinter as ctk

        ctk.CTkLabel(
            parent, text="API Key", font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            parent,
            text=(
                "To use the English Coach, you need a free API key from DeepSeek.\n"
                "Get one at: platform.deepseek.com"
            ),
            font=("Segoe UI", 13),
            wraplength=500,
            justify="center",
        ).pack(pady=(0, 20))

        ctk.CTkLabel(
            parent, text="DeepSeek API Key", font=("Segoe UI", 13)
        ).pack(anchor="w", padx=30)

        api_entry = ctk.CTkEntry(
            parent, width=400, height=35,
            placeholder_text="sk-...",
            show="*",
        )
        api_entry.pack(pady=(5, 5))

        if DEEPSEEK_API_KEY:
            api_entry.insert(0, DEEPSEEK_API_KEY)

        self._widgets["api_entry"] = api_entry

        show_btn = ctk.CTkButton(
            parent,
            text="Show/Hide Key",
            width=130,
            font=("Segoe UI", 11),
            command=lambda: self._toggle_api_visibility(api_entry),
            fg_color="gray40",
        )
        show_btn.pack(pady=(5, 20))

        ctk.CTkLabel(
            parent,
            text="You can skip this and add it to the .env file later.",
            font=("Segoe UI", 11),
            text_color="gray60",
        ).pack()

        self._on_leave_step = self._save_api_key

    def _toggle_api_visibility(self, entry):
        import customtkinter as ctk
        if entry.cget("show") == "*":
            entry.configure(show="")
        else:
            entry.configure(show="*")

    def _save_api_key(self):
        api_key = self._widgets["api_entry"].get().strip()
        if api_key and api_key != DEEPSEEK_API_KEY:
            # Write to .env file
            env_path = Path(__file__).parent.parent / ".env"
            self._update_env_file(env_path, "DEEPSEEK_API_KEY", api_key)

    def _update_env_file(self, env_path: Path, key: str, value: str):
        """Update or add a variable in the .env file."""
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            env_path.write_text(f"{key}={value}\n", encoding="utf-8")

        logger.info(f"Updated {key} in .env file")

    # === Override _show_step to handle on_leave ===

    def _show_step(self, index: int):
        """Override: save data from previous step before showing new one."""
        if hasattr(self, '_on_leave_step') and callable(self._on_leave_step):
            try:
                self._on_leave_step()
            except Exception as e:
                logger.warning(f"Error saving step data: {e}")

        # Call the original logic
        import customtkinter as ctk

        for widget in self._widgets.values():
            widget.pack_forget()

        self._widgets.clear()
        self._current_step = index
        step = self._steps[index]

        self._back_btn.pack_forget()
        self._next_btn.pack_forget()
        if hasattr(self, '_finish_btn') and self._finish_btn:
            self._finish_btn.pack_forget()

        if index > 0:
            self._back_btn.pack(side="left", padx=(0, 10))

        if index < len(self._steps) - 1:
            self._next_btn.pack(side="right", padx=(10, 0))
        else:
            self._finish_btn = ctk.CTkButton(
                self._nav_frame,
                text="Finish Setup",
                width=120,
                command=self._finish,
                fg_color="#2E8B57",
            )
            self._finish_btn.pack(side="right", padx=(10, 0))

        content_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=40, pady=(30, 10))
        self._widgets["content_frame"] = content_frame

        step["content"](content_frame)


def run_setup_wizard():
    """Entry point to run the setup wizard standalone."""
    try:
        import customtkinter as ctk

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        root = ctk.CTk()
        wizard = SetupWizard(root)
        root.mainloop()
    except ImportError:
        print("[ERROR] customtkinter not installed. Run: pip install customtkinter")
        print("[INFO] Running CLI fallback setup...")
        _cli_fallback()


def _cli_fallback():
    """Fallback CLI setup when GUI is unavailable."""
    import json

    from config.settings import DATA_DIR

    print("\n=== English Coach Agent — CLI Setup ===\n")

    name = input("Your preferred name: ").strip() or "there"
    print(f"\nHi {name}! Let's set up your profile.\n")

    print("English level:")
    print("  1) Beginner — I know basic words and phrases")
    print("  2) Intermediate — I can hold simple conversations")
    print("  3) Upper-intermediate — I can discuss most topics")
    print("  4) Advanced — I'm fluent, want to refine")
    level_choice = input("Choose (1-4) [2]: ").strip() or "2"
    level_map = {"1": "beginner", "2": "intermediate", "3": "upper_intermediate", "4": "advanced"}
    level = level_map.get(level_choice, "intermediate")

    role = input("\nYour professional role: ").strip() or "Professional"
    company = input("Company (optional): ").strip()
    interests_raw = input("Topics you enjoy (comma-separated): ").strip() or "technology, travel"
    interests = [t.strip() for t in interests_raw.split(",") if t.strip()]

    print("\nCorrection style:")
    print("  1) Immediate — correct as you speak")
    print("  2) Gentle — acknowledge first, then suggest (recommended)")
    print("  3) End of sentence — wait until you finish, then correct")
    style_choice = input("Choose (1-3) [2]: ").strip() or "2"
    style_map = {"1": "immediate", "2": "gentle", "3": "end_of_sentence"}
    correction_style = style_map.get(style_choice, "gentle")

    print("\nVoice options:")
    print("  1) Aria — American female (default)")
    print("  2) Guy — American male")
    print("  3) Sonia — British female")
    print("  4) Natasha — Australian female")
    voice_choice = input("Choose (1-4) [1]: ").strip() or "1"
    voice_map = {
        "1": "en-US-AriaNeural", "2": "en-US-GuyNeural",
        "3": "en-GB-SoniaNeural", "4": "en-AU-NatashaNeural",
    }
    voice = voice_map.get(voice_choice, "en-US-AriaNeural")

    api_key = input("\nDeepSeek API Key (from platform.deepseek.com): ").strip()

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
            "topics_of_interest": interests,
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
            "correction_style": correction_style,
            "spontaneous_triggers_enabled": True,
            "spontaneous_interval_minutes": 60,
            "daily_checkin_time": "09:00",
            "tts_voice": voice,
            "ui_always_on_top": True,
        },
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "profile_version": "1.0.0",
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = DATA_DIR / "profile.json"
    profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    print(f"\n[OK] Profile saved to {profile_path}")

    if api_key:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text()
            if "DEEPSEEK_API_KEY=" not in content:
                env_path.write_text(f"{content}\nDEEPSEEK_API_KEY={api_key}\n")
        else:
            env_path.write_text(f"DEEPSEEK_API_KEY={api_key}\n")
        print(f"[OK] API key saved to .env")

    print("\nSetup complete! Run: python run.py\n")


if __name__ == "__main__":
    run_setup_wizard()
