"""
Transcription panel — displays real-time conversation with correction highlights.
Shows user speech, agent responses, and grammar corrections in distinct colors.
"""

import customtkinter as ctk

from ui.theme import AppTheme


class TranscriptionPanel(ctk.CTkFrame):
    """
    Real-time transcription display panel.
    Shows user speech and agent responses with correction highlights.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=AppTheme.BG_DARK, **kwargs)

        self._entries: list[dict] = []  # [{role, text, corrections, timestamp}]
        self._max_entries = 100

        self._build_ui()

    def _build_ui(self):
        """Build the panel layout."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=30)
        header.pack(fill="x", padx=AppTheme.PADDING_MD, pady=(AppTheme.PADDING_SM, 0))

        ctk.CTkLabel(
            header,
            text="Transcription",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
        ).pack(side="left")

        self._clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            height=24,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.BG_CARD,
            command=self.clear,
        )
        self._clear_btn.pack(side="right")

        # Scrollable text area
        self._text_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=AppTheme.BG_DARKER,
            corner_radius=6,
        )
        self._text_frame.pack(
            fill="both", expand=True,
            padx=AppTheme.PADDING_MD,
            pady=AppTheme.PADDING_MD,
        )

        # Inner frame for messages (to pack top-to-bottom)
        self._messages_frame = ctk.CTkFrame(
            self._text_frame, fg_color="transparent"
        )
        self._messages_frame.pack(fill="both", expand=True)

    def add_user_text(self, text: str):
        """Add user's transcribed speech to the panel."""
        if not text.strip():
            return

        self._entries.append({
            "role": "user",
            "text": text,
            "corrections": [],
            "timestamp": "",
        })

        self._render_entry("user", text)

        self._trim_entries()
        self._scroll_to_bottom()

    def add_agent_text(self, text: str, corrections: list | None = None):
        """Add agent's response to the panel with optional correction highlights."""
        if not text.strip() and not corrections:
            return

        entry = {
            "role": "agent",
            "text": text,
            "corrections": corrections or [],
            "timestamp": "",
        }
        self._entries.append(entry)

        self._render_entry("agent", text, corrections)

        self._render_corrections(corrections)

        self._trim_entries()
        self._scroll_to_bottom()

    def add_correction(self, correction):
        """Add a single correction highlight."""
        if hasattr(correction, "original"):
            # ParsedCorrection or Correction object
            self._render_correction_inline(
                original=correction.original,
                corrected=correction.corrected,
                explanation=correction.explanation,
                error_type=getattr(correction, "error_type", "grammar"),
            )
        elif isinstance(correction, dict):
            self._render_correction_inline(
                original=correction.get("original", ""),
                corrected=correction.get("corrected", ""),
                explanation=correction.get("explanation", ""),
                error_type=correction.get("error_type", "grammar"),
            )

    def add_system_message(self, text: str, color: str | None = None):
        """Add a system message (status, error, etc.)."""
        color = color or AppTheme.TEXT_MUTED

        frame = ctk.CTkFrame(self._messages_frame, fg_color="transparent")
        frame.pack(fill="x", padx=AppTheme.PADDING_MD, pady=2)

        ctk.CTkLabel(
            frame,
            text=f"  {text}",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            text_color=color,
            anchor="w",
        ).pack(fill="x")

        self._scroll_to_bottom()

    def _render_entry(self, role: str, text: str, corrections: list | None = None):
        """Render a conversation entry."""
        color = AppTheme.TEXT_USER if role == "user" else AppTheme.TEXT_AGENT
        label = "You" if role == "user" else "Aria"

        frame = ctk.CTkFrame(self._messages_frame, fg_color="transparent")
        frame.pack(fill="x", padx=AppTheme.PADDING_MD, pady=(AppTheme.PADDING_SM, 0))

        # Role label
        ctk.CTkLabel(
            frame,
            text=f"{label}:",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY, "bold"),
            text_color=color,
            anchor="w",
        ).pack(anchor="w")

        # Text content
        ctk.CTkLabel(
            frame,
            text=text.strip(),
            font=(AppTheme.FONT_MONO, AppTheme.FONT_SIZE_TRANSCRIPTION),
            text_color=AppTheme.TEXT_PRIMARY if role == "user" else AppTheme.TEXT_AGENT,
            anchor="w",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=(AppTheme.PADDING_LG, 0))

    def _render_corrections(self, corrections: list | None):
        """Render correction highlights."""
        if not corrections:
            return

        for c in corrections:
            self.add_correction(c)

    def _render_correction_inline(
        self, original: str, corrected: str, explanation: str, error_type: str = "grammar"
    ):
        """Render a single correction as a highlighted card."""
        frame = ctk.CTkFrame(
            self._messages_frame,
            fg_color=AppTheme.BG_CARD,
            corner_radius=4,
        )
        frame.pack(fill="x", padx=AppTheme.PADDING_XL + 20, pady=2)

        # Error type badge
        badge_frame = ctk.CTkFrame(frame, fg_color="transparent")
        badge_frame.pack(fill="x", padx=AppTheme.PADDING_SM, pady=(2, 0))

        ctk.CTkLabel(
            badge_frame,
            text=f" {error_type.upper()} ",
            font=(AppTheme.FONT_FAMILY, 9, "bold"),
            text_color=AppTheme.TEXT_CORRECTION,
        ).pack(side="left")

        # Original → Corrected
        text = f"'{original}'  →  '{corrected}'"
        ctk.CTkLabel(
            frame,
            text=text,
            font=(AppTheme.FONT_MONO, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_CORRECTION,
            anchor="w",
            wraplength=650,
        ).pack(fill="x", padx=AppTheme.PADDING_MD, pady=(0, 2))

        # Explanation
        if explanation:
            ctk.CTkLabel(
                frame,
                text=explanation,
                font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
                text_color=AppTheme.TEXT_SECONDARY,
                anchor="w",
                wraplength=650,
            ).pack(fill="x", padx=AppTheme.PADDING_MD, pady=(0, 4))

    def _trim_entries(self):
        """Remove old entries if exceeding max."""
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the text area."""
        self._text_frame._parent_canvas.yview_moveto(1.0)

    def clear(self):
        """Clear all transcription entries."""
        self._entries.clear()

        for widget in self._messages_frame.winfo_children():
            widget.destroy()

    def get_text(self) -> str:
        """Get the full conversation as plain text (for session summary)."""
        lines = []
        for entry in self._entries:
            role = "You" if entry["role"] == "user" else "Aria"
            lines.append(f"{role}: {entry['text']}")
        return "\n".join(lines)
