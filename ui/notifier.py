"""
Windows/Linux notification handler for the English Coach Agent.
Shows native OS notifications when the agent wants to start a conversation,
remind about streaks, or alert about check-ins.

Uses plyer (cross-platform) with Windows toast fallback.
"""

import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path

from config.logging_config import setup_logging

logger = setup_logging()


class NotificationType:
    SPONTANEOUS = "spontaneous"
    DAILY_CHECKIN = "daily_checkin"
    STREAK_REMINDER = "streak_reminder"
    GRAMMAR_SUGGESTION = "grammar_suggestion"
    SYSTEM = "system"


class Notifier:
    """
    Cross-platform desktop notification handler.
    Sends OS-native notifications for agent events.
    Rate-limited to avoid notification fatigue.
    """

    # Minimum minutes between notifications
    MIN_INTERVAL_MINUTES = 60

    def __init__(self):
        self._last_notification: datetime | None = None
        self._on_click_callbacks: list[callable] = []
        self._project_root = Path(__file__).parent.parent
        self._icon_path = str(self._project_root / "assets" / "icon.ico")
        self._enabled = True

    def on_click(self, callback: callable):
        """Register callback for when user clicks a notification."""
        self._on_click_callbacks.append(callback)

    def show(
        self,
        title: str,
        message: str,
        notification_type: str = NotificationType.SYSTEM,
        duration: int = 5,
    ):
        """
        Show a desktop notification.

        Args:
            title: Notification title
            message: Notification body text
            notification_type: Type category for rate limiting
            duration: Display duration in seconds
        """
        if not self._enabled:
            return

        # Rate limiting — max 1 notification per hour (except system msgs)
        if notification_type != NotificationType.SYSTEM and self._last_notification:
            since_last = (datetime.now() - self._last_notification).total_seconds()
            if since_last < self.MIN_INTERVAL_MINUTES * 60:
                logger.debug(
                    f"Notification suppressed (rate limited): {title}"
                )
                return

        self._last_notification = datetime.now()

        # Run notification in a separate thread to avoid blocking
        thread = threading.Thread(
            target=self._show_notification,
            args=(title, message, notification_type, duration),
            daemon=True,
        )
        thread.start()

    def _show_notification(
        self, title: str, message: str, ntype: str, duration: int
    ):
        """Internal: show notification using best available method."""
        try:
            self._show_with_plyer(title, message, duration)
        except Exception as e:
            logger.debug(f"plyer notification failed: {e}")
            try:
                self._show_with_win10toast(title, message, duration)
            except Exception as e2:
                logger.debug(f"win10toast notification failed: {e2}")
                self._log_notification(title, message)

    def _show_with_plyer(self, title: str, message: str, duration: int):
        """Show notification using plyer (cross-platform)."""
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="English Coach Agent",
            app_icon=self._icon_path if Path(self._icon_path).exists() else None,
            timeout=duration,
            ticker="English Coach Agent",
        )

        logger.info(f"Notification shown: {title}")

    def _show_with_win10toast(self, title: str, message: str, duration: int):
        """Show notification using win10toast on Windows."""
        from win10toast import ToastNotifier

        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            icon_path=self._icon_path if Path(self._icon_path).exists() else None,
            duration=duration,
            threaded=True,
        )

        logger.info(f"Toast notification shown: {title}")

    def _log_notification(self, title: str, message: str):
        """Fallback: log notification when GUI methods fail."""
        logger.info(f"[NOTIFICATION] {title}: {message}")

    # === Convenience methods ===

    def notify_spontaneous_trigger(self, topic_hint: str = ""):
        """Notify that the agent wants to chat spontaneously."""
        title = "Aria wants to chat!"
        message = "Your English coach has something to talk about."

        if topic_hint:
            message = f"Let's talk about {topic_hint}"

        self.show(
            title=title,
            message=message,
            notification_type=NotificationType.SPONTANEOUS,
        )

    def notify_daily_checkin(self, user_name: str = ""):
        """Notify about the daily check-in."""
        greeting = f"Good morning{f', {user_name}' if user_name else ''}!"
        title = f"{greeting}"
        message = "Ready for your daily English practice?"

        self.show(
            title=title,
            message=message,
            notification_type=NotificationType.DAILY_CHECKIN,
        )

    def notify_streak(self, days: int):
        """Notify about practice streak."""
        title = f"🔥 {days} day streak!"
        message = "Keep it going — your English coach is waiting."

        self.show(
            title=title,
            message=message,
            notification_type=NotificationType.STREAK_REMINDER,
        )

    def notify_grammar_suggestion(self, topic: str):
        """Notify about a suggested grammar topic to practice."""
        title = "Study suggestion"
        message = f"Let's practice: {topic}"

        self.show(
            title=title,
            message=message,
            notification_type=NotificationType.GRAMMAR_SUGGESTION,
        )

    def notify_system(self, title: str, message: str):
        """Show a system notification (error, status, etc.)."""
        self.show(
            title=title,
            message=message,
            notification_type=NotificationType.SYSTEM,
        )

    # === Controls ===

    def set_enabled(self, enabled: bool):
        """Enable or disable notifications."""
        self._enabled = enabled
        if not enabled:
            logger.info("Notifications disabled")
        else:
            logger.info("Notifications enabled")

    def test(self):
        """Send a test notification to verify setup."""
        self.show(
            title="English Coach Agent",
            message="Notifications are working!",
            notification_type=NotificationType.SYSTEM,
        )
