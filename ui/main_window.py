"""
Main application window for the English Coach Agent.
Floating overlay window with transcription, status indicator, and controls.
"""

import asyncio
import threading
from datetime import datetime

import customtkinter as ctk

from ui.theme import AppTheme
from ui.transcription_panel import TranscriptionPanel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainWindow:
    """
    Main overlay window for the English Coach Agent.
    Displays live transcription, corrections, status, and controls.
    """

    def __init__(self, agent=None):
        self.agent = agent  # EnglishCoachAgent instance

        # Create the main window
        self.root = ctk.CTk()
        self.root.title("English Coach Agent (ECA-1)")

        # Window size and position
        self.root.geometry(f"{AppTheme.WINDOW_WIDTH}x{AppTheme.WINDOW_HEIGHT}")

        # Always on top
        self._always_on_top = True
        self.root.attributes("-topmost", self._always_on_top)

        # Center on screen
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - AppTheme.WINDOW_WIDTH) // 2
        y = (screen_h - AppTheme.WINDOW_HEIGHT) // 2
        self.root.geometry(f"+{x}+{y}")

        # Minimum size
        self.root.minsize(AppTheme.WINDOW_MIN_WIDTH, AppTheme.WINDOW_MIN_HEIGHT)

        # Window protocol
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # State
        self._paused = False
        self._current_state = "IDLE"

        # Build UI
        self._build_ui()

        # Stats data
        self._session_corrections = 0

    def _build_ui(self):
        """Build the complete window layout."""
        # === Status bar (top) ===
        self._status_bar = ctk.CTkFrame(
            self.root,
            height=AppTheme.STATUS_BAR_HEIGHT,
            fg_color=AppTheme.STATUS_IDLE,
            corner_radius=0,
        )
        self._status_bar.pack(fill="x")

        # === Header with status label and controls ===
        header = ctk.CTkFrame(self.root, fg_color=AppTheme.BG_DARKER, height=36)
        header.pack(fill="x")

        # Status indicator (colored dot + label)
        self._status_indicator = ctk.CTkLabel(
            header,
            text="  Idle",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY,
        )
        self._status_indicator.pack(side="left", padx=AppTheme.PADDING_MD)

        # Session time
        self._time_label = ctk.CTkLabel(
            header,
            text="00:00",
            font=(AppTheme.FONT_MONO, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY,
        )
        self._time_label.pack(side="left", padx=(0, AppTheme.PADDING_MD))

        # Correction counter
        self._correction_label = ctk.CTkLabel(
            header,
            text="0 corrections",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            text_color=AppTheme.TEXT_CORRECTION,
        )
        self._correction_label.pack(side="left", padx=(0, AppTheme.PADDING_MD))

        # Spacer
        ctk.CTkLabel(header, text="").pack(side="left", fill="x", expand=True)

        # Pause / Resume button
        self._pause_btn = ctk.CTkButton(
            header,
            text="Pause",
            width=70,
            height=26,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.BG_CARD,
            command=self._toggle_pause,
        )
        self._pause_btn.pack(side="right", padx=(0, AppTheme.PADDING_MD))

        # Minimize to tray button
        self._minimize_btn = ctk.CTkButton(
            header,
            text="—",
            width=30,
            height=26,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            fg_color=AppTheme.BG_CARD,
            command=self._minimize_to_tray,
        )
        self._minimize_btn.pack(side="right", padx=(0, AppTheme.PADDING_SM))

        # Always on top toggle
        self._pin_btn = ctk.CTkButton(
            header,
            text="📌",
            width=30,
            height=26,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.ACCENT_SUCCESS if self._always_on_top else AppTheme.BG_CARD,
            command=self._toggle_always_on_top,
        )
        self._pin_btn.pack(side="right", padx=(0, AppTheme.PADDING_SM))

        # === Main content area ===
        content = ctk.CTkFrame(self.root, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Left: Transcription panel (70%)
        self._transcription = TranscriptionPanel(content)
        self._transcription.pack(
            side="left", fill="both", expand=True,
            padx=(AppTheme.PADDING_MD, AppTheme.PADDING_SM),
            pady=AppTheme.PADDING_MD,
        )

        # Right: Sidebar with stats/modes
        sidebar = ctk.CTkFrame(content, fg_color=AppTheme.BG_DARKER, width=200)
        sidebar.pack(
            side="right", fill="y",
            padx=(AppTheme.PADDING_SM, AppTheme.PADDING_MD),
            pady=AppTheme.PADDING_MD,
        )
        sidebar.pack_propagate(False)

        self._build_sidebar(sidebar)

    def _build_sidebar(self, parent):
        """Build the right sidebar with stats and quick info."""
        # Mode indicator
        mode_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mode_frame.pack(fill="x", padx=AppTheme.PADDING_MD, pady=(AppTheme.PADDING_MD, AppTheme.PADDING_SM))

        ctk.CTkLabel(
            mode_frame,
            text="Session",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
        ).pack(anchor="w")

        # Stats
        self._sidebar_turns_label = ctk.CTkLabel(
            parent,
            text="Turns: 0",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY,
            anchor="w",
        )
        self._sidebar_turns_label.pack(fill="x", padx=AppTheme.PADDING_MD, pady=2)

        self._sidebar_corrections_label = ctk.CTkLabel(
            parent,
            text="Corrections: 0",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY,
            anchor="w",
        )
        self._sidebar_corrections_label.pack(fill="x", padx=AppTheme.PADDING_MD, pady=2)

        # Separator
        ctk.CTkFrame(
            parent, height=1, fg_color=AppTheme.BG_CARD
        ).pack(fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD)

        # Profile summary
        ctk.CTkLabel(
            parent,
            text="Profile",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
        ).pack(anchor="w", padx=AppTheme.PADDING_MD)

        self._profile_name_label = ctk.CTkLabel(
            parent,
            text="User: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            text_color=AppTheme.TEXT_SECONDARY,
            anchor="w",
        )
        self._profile_name_label.pack(fill="x", padx=AppTheme.PADDING_MD, pady=1)

        self._profile_level_label = ctk.CTkLabel(
            parent,
            text="Level: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            text_color=AppTheme.TEXT_SECONDARY,
            anchor="w",
        )
        self._profile_level_label.pack(fill="x", padx=AppTheme.PADDING_MD, pady=1)

        # Spacer
        ctk.CTkLabel(parent, text="").pack(fill="y", expand=True)

        # Bottom buttons
        ctk.CTkButton(
            parent,
            text="Setup Wizard",
            width=160,
            height=26,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.BG_CARD,
            command=self._run_wizard,
        ).pack(padx=AppTheme.PADDING_MD, pady=(0, 4))

        ctk.CTkButton(
            parent,
            text="Quit Agent",
            width=160,
            height=26,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.ACCENT_DANGER,
            command=self._on_close,
        ).pack(padx=AppTheme.PADDING_MD, pady=(0, AppTheme.PADDING_MD))

    # === State updates ===

    def update_state(self, new_state, old_state=None):
        """Update the status bar and indicator based on pipeline state."""
        self._current_state = new_state.name if hasattr(new_state, 'name') else str(new_state)
        color = AppTheme.get_status_color(self._current_state)
        label = AppTheme.get_status_label(self._current_state)

        self._status_bar.configure(fg_color=color)
        self._status_indicator.configure(text=f"  {label}", text_color=color)

        # Auto-update pause button
        if self._current_state == "PAUSED":
            self._paused = True
            self._pause_btn.configure(text="Resume", fg_color=AppTheme.ACCENT_SUCCESS)
        elif self._paused and self._current_state != "PAUSED":
            self._paused = False
            self._pause_btn.configure(text="Pause", fg_color=AppTheme.BG_CARD)

    def update_transcription(self, text: str):
        """Show user's transcribed speech."""
        self._transcription.add_user_text(text)

    def update_response(self, processed):
        """Show agent's response with corrections."""
        text = processed.conversational_text if hasattr(processed, 'conversational_text') else processed
        corrections = processed.corrections if hasattr(processed, 'corrections') else []

        self._transcription.add_agent_text(text, corrections)

    def update_correction(self, correction):
        """Show a single correction highlight."""
        self._transcription.add_correction(correction)
        self._session_corrections += 1
        self._correction_label.configure(text=f"{self._session_corrections} corrections")
        self._sidebar_corrections_label.configure(
            text=f"Corrections: {self._session_corrections}"
        )

    def update_turn(self, result):
        """Update turn counter."""
        if hasattr(result, 'total_turns'):
            self._sidebar_turns_label.configure(text=f"Turns: {result.total_turns}")
        else:
            # Increment counter
            current = int(self._sidebar_turns_label.cget("text").split(": ")[-1])
            self._sidebar_turns_label.configure(text=f"Turns: {current + 1}")

    def update_profile(self, profile: dict):
        """Update profile summary in sidebar."""
        user = profile.get("user", {})
        eng = profile.get("english_profile", {})

        name = user.get("name", "—")
        level = eng.get("current_level", "—")

        self._profile_name_label.configure(text=f"User: {name}")
        self._profile_level_label.configure(text=f"Level: {level}")

    def show_error(self, error_msg: str):
        """Show error in transcription panel."""
        self._transcription.add_system_message(f"Error: {error_msg}", AppTheme.TEXT_ERROR)

    def show_system_message(self, text: str):
        """Show system message in transcription."""
        self._transcription.add_system_message(text)

    # === Controls ===

    def _toggle_pause(self):
        """Toggle pause/resume."""
        if self._paused:
            if self.agent:
                self.agent.resume()
            self._paused = False
            self._pause_btn.configure(text="Pause", fg_color=AppTheme.BG_CARD)
            self._transcription.add_system_message("Agent resumed")
        else:
            if self.agent:
                self.agent.pause()
            self._paused = True
            self._pause_btn.configure(text="Resume", fg_color=AppTheme.ACCENT_SUCCESS)
            self._transcription.add_system_message("Agent paused")

    def _toggle_always_on_top(self):
        """Toggle always on top."""
        self._always_on_top = not self._always_on_top
        self.root.attributes("-topmost", self._always_on_top)
        self._pin_btn.configure(
            fg_color=AppTheme.ACCENT_SUCCESS if self._always_on_top else AppTheme.BG_CARD
        )

    def _minimize_to_tray(self):
        """Minimize to system tray."""
        self.root.withdraw()  # Hide window

    def restore_from_tray(self):
        """Restore window from tray."""
        self.root.deiconify()
        self.root.lift()

    def _run_wizard(self):
        """Run the setup wizard from settings."""
        from ui.setup_wizard import run_setup_wizard
        # Run wizard in a new thread to avoid blocking the agent
        threading.Thread(target=run_setup_wizard, daemon=True).start()

    def _on_close(self):
        """Handle window close — minimize to tray or quit."""
        # On Windows, minimize to tray instead of closing
        self._minimize_to_tray()

    def quit(self):
        """Fully close the application."""
        if self.agent:
            asyncio.create_task(self.agent.stop())
        self.root.quit()
        self.root.destroy()

    # === Lifecycle ===

    def start(self):
        """Start the window main loop."""
        self.root.mainloop()

    def schedule_update(self, callback, *args):
        """Schedule a UI update from async context."""
        self.root.after(0, callback, *args)

    # === Session timer ===

    def _start_timer(self):
        """Start the session time counter."""
        self._session_start_time = datetime.now()
        self._update_timer()

    def _update_timer(self):
        """Update the session time label."""
        if hasattr(self, '_session_start_time'):
            elapsed = (datetime.now() - self._session_start_time).seconds
            minutes = elapsed // 60
            seconds = elapsed % 60
            self._time_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        self.root.after(1000, self._update_timer)
