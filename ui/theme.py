"""
UI Theme constants for the English Coach Agent.
Defines colors, fonts, and styling used across all UI components.
"""

from enum import Enum


class AppTheme:
    """Central theme definition for the application."""

    # Background colors
    BG_DARK = "#1a1a2e"
    BG_DARKER = "#16213e"
    BG_CARD = "#0f3460"
    BG_INPUT = "#1a1a3e"

    # Status bar colors
    STATUS_LISTENING = "#2ecc71"   # Green — detecting speech
    STATUS_TRANSCRIBING = "#3498db" # Blue — processing audio
    STATUS_THINKING = "#9b59b6"     # Purple — LLM thinking
    STATUS_SPEAKING = "#e67e22"    # Orange — playing audio
    STATUS_PAUSED = "#7f8c8d"      # Gray — paused
    STATUS_IDLE = "#95a5a6"        # Light gray — idle
    STATUS_ERROR = "#e74c3c"       # Red — error

    # Text colors
    TEXT_PRIMARY = "#ecf0f1"
    TEXT_SECONDARY = "#bdc3c7"
    TEXT_MUTED = "#7f8c8d"
    TEXT_USER = "#ffffff"          # User speech in transcription
    TEXT_AGENT = "#3498db"         # Agent speech
    TEXT_CORRECTION = "#e67e22"    # Highlighted corrections
    TEXT_ERROR = "#f1c40f"         # Error messages

    # Accent colors
    ACCENT_PRIMARY = "#3498db"
    ACCENT_SUCCESS = "#2ecc71"
    ACCENT_WARNING = "#f39c12"
    ACCENT_DANGER = "#e74c3c"

    # Fonts
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"
    FONT_SIZE_TITLE = 18
    FONT_SIZE_HEADING = 14
    FONT_SIZE_BODY = 12
    FONT_SIZE_SMALL = 10
    FONT_SIZE_TRANSCRIPTION = 13

    # Spacing
    PADDING_SM = 5
    PADDING_MD = 10
    PADDING_LG = 15
    PADDING_XL = 20

    # Window
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 500
    WINDOW_MIN_WIDTH = 600
    WINDOW_MIN_HEIGHT = 400

    # Status bar
    STATUS_BAR_HEIGHT = 4

    @classmethod
    def get_status_color(cls, state_name: str) -> str:
        """Get the color for a pipeline state."""
        state_colors = {
            "IDLE": cls.STATUS_IDLE,
            "LISTENING": cls.STATUS_LISTENING,
            "TRANSCRIBING": cls.STATUS_TRANSCRIBING,
            "THINKING": cls.STATUS_THINKING,
            "SPEAKING": cls.STATUS_SPEAKING,
            "PAUSED": cls.STATUS_PAUSED,
            "ERROR": cls.STATUS_ERROR,
        }
        return state_colors.get(state_name.upper(), cls.STATUS_IDLE)

    @classmethod
    def get_status_label(cls, state_name: str) -> str:
        """Get a human-readable label for a pipeline state."""
        labels = {
            "IDLE": "Idle",
            "LISTENING": "Listening...",
            "TRANSCRIBING": "Transcribing...",
            "THINKING": "Thinking...",
            "SPEAKING": "Speaking...",
            "PAUSED": "Paused",
            "ERROR": "Error",
        }
        return labels.get(state_name.upper(), state_name)
