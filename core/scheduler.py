"""
Spontaneous trigger scheduler for the English Coach Agent.
Schedules and executes spontaneous conversation initiations.
Supports random intervals, daily check-ins, and post-silence triggers.
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Optional, Callable

from config.settings import (
    SPONTANEOUS_ENABLED,
    SPONTANEOUS_MIN_MINUTES,
    SPONTANEOUS_MAX_MINUTES,
    ACTIVE_HOURS_START,
    ACTIVE_HOURS_END,
)
from config.logging_config import setup_logging

logger = setup_logging()


class TriggerType(str, Enum):
    RANDOM_INTERVAL = "random_interval"
    DAILY_CHECKIN = "daily_checkin"
    POST_SILENCE = "post_silence"
    MANUAL = "manual"
    SCHEDULER = "scheduler"


@dataclass
class TriggerConfig:
    enabled: bool = True
    min_minutes: int = SPONTANEOUS_MIN_MINUTES
    max_minutes: int = SPONTANEOUS_MAX_MINUTES
    active_start_hour: int = ACTIVE_HOURS_START
    active_end_hour: int = ACTIVE_HOURS_END
    daily_checkin_time: str = "09:00"
    post_silence_minutes: int = 60
    availability_check: bool = True


@dataclass
class TriggerEvent:
    trigger_type: TriggerType
    scheduled_at: datetime | None = None
    fired_at: datetime | None = None
    topic: str = ""
    user_responded: bool = False
    session_id: int | None = None


class SpontaneousScheduler:
    """
    Schedules spontaneous conversation triggers.
    Works alongside the main agent pipeline to create natural
    conversation openings throughout the day.
    """

    def __init__(self, config: TriggerConfig | None = None):
        self.config = config or TriggerConfig()
        self._running = False
        self._next_trigger_time: datetime | None = None
        self._trigger_task: asyncio.Task | None = None
        self._checkin_task: asyncio.Task | None = None
        self._last_trigger: datetime | None = None
        self._trigger_count_today = 0
        self._max_triggers_per_day = 10

        # Callbacks
        self._on_trigger: list[Callable] = []
        self._on_availability_response: list[Callable] = []

        # Silence tracking
        self._last_user_activity: datetime | None = None
        self._silence_task: asyncio.Task | None = None

    # === Callback registration ===

    def on_trigger(self, callback: Callable):
        """Register callback for when a trigger fires.
        Callback receives (TriggerEvent)."""
        self._on_trigger.append(callback)

    # === Lifecycle ===

    async def start(self):
        """Start the scheduler."""
        if not self.config.enabled:
            logger.info("Spontaneous mode is disabled. Skipping scheduler.")
            return

        self._running = True
        logger.info(
            f"Spontaneous scheduler started "
            f"(interval: {self.config.min_minutes}-{self.config.max_minutes} min, "
            f"active: {self.config.active_start_hour:02d}:00-{self.config.active_end_hour:02d}:00)"
        )

        # Start random interval trigger loop
        self._trigger_task = asyncio.create_task(self._random_interval_loop())

        # Start daily check-in watcher
        self._checkin_task = asyncio.create_task(self._daily_checkin_loop())

        # Start silence watcher
        self._silence_task = asyncio.create_task(self._silence_watcher())

    async def stop(self):
        """Stop the scheduler."""
        self._running = False

        for task in [self._trigger_task, self._checkin_task, self._silence_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("Spontaneous scheduler stopped")

    # === Core loops ===

    async def _random_interval_loop(self):
        """Main loop that fires triggers at random intervals."""
        while self._running:
            try:
                # Wait for a random interval
                delay_minutes = random.randint(
                    self.config.min_minutes,
                    self.config.max_minutes,
                )

                self._next_trigger_time = datetime.now() + asyncio.timedelta(
                    minutes=delay_minutes
                )

                logger.debug(
                    f"Next spontaneous trigger in {delay_minutes} minutes "
                    f"(at {self._next_trigger_time.strftime('%H:%M')})"
                )

                # Wait
                await asyncio.sleep(delay_minutes * 60)

                if not self._running:
                    break

                # Check if within active hours
                if not self._is_active_hours():
                    logger.debug("Outside active hours, skipping trigger")
                    continue

                # Fire trigger
                await self._fire_trigger(TriggerType.RANDOM_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _daily_checkin_loop(self):
        """Loop that watches for the daily check-in time."""
        while self._running:
            try:
                # Parse check-in time
                checkin_str = self.config.daily_checkin_time
                if not checkin_str or ":" not in checkin_str:
                    await asyncio.sleep(300)  # Wait 5 min and retry
                    continue

                hour, minute = map(int, checkin_str.split(":"))
                checkin_time = time(hour=hour, minute=minute)

                # Calculate seconds until next check-in
                now = datetime.now()
                next_checkin = datetime.combine(now.date(), checkin_time)

                if next_checkin <= now:
                    # Already passed today, schedule for tomorrow
                    next_checkin = next_checkin.replace(
                        day=next_checkin.day + 1
                    )

                wait_seconds = (next_checkin - now).total_seconds()

                logger.debug(
                    f"Daily check-in scheduled for "
                    f"{next_checkin.strftime('%Y-%m-%d %H:%M')} "
                    f"({wait_seconds / 3600:.1f} hours from now)"
                )

                # Wait until check-in time
                await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                # Fire the daily check-in
                if self._is_active_hours():
                    await self._fire_trigger(TriggerType.DAILY_CHECKIN)
                else:
                    logger.debug("Check-in time but outside active hours")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Check-in loop error: {e}")
                await asyncio.sleep(300)

    async def _silence_watcher(self):
        """Watch for extended post-silence to trigger conversation."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute

                if not self._running or not self._is_active_hours():
                    continue

                if self._last_user_activity is None:
                    continue

                silence_minutes = (
                    datetime.now() - self._last_user_activity
                ).total_seconds() / 60

                if silence_minutes >= self.config.post_silence_minutes:
                    logger.info(
                        f"User inactive for {silence_minutes:.0f} minutes. "
                        "Triggering post-silence conversation."
                    )
                    await self._fire_trigger(TriggerType.POST_SILENCE)
                    self._last_user_activity = None  # Reset to avoid spam

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Silence watcher error: {e}")

    # === Trigger execution ===

    async def _fire_trigger(self, trigger_type: TriggerType):
        """
        Fire a spontaneous trigger.
        Notifies all callbacks and creates a TriggerEvent.
        """
        # Rate limiting: max triggers per day
        if self._trigger_count_today >= self._max_triggers_per_day:
            logger.debug("Max daily triggers reached, skipping")
            return

        # Don't fire if a trigger was very recent (within 5 minutes)
        if self._last_trigger:
            since_last = (datetime.now() - self._last_trigger).total_seconds()
            if since_last < 300:  # 5 minutes
                logger.debug("Too soon since last trigger, skipping")
                return

        self._last_trigger = datetime.now()
        self._trigger_count_today += 1

        event = TriggerEvent(
            trigger_type=trigger_type,
            scheduled_at=self._next_trigger_time,
            fired_at=datetime.now(),
        )

        logger.info(
            f"Spontaneous trigger fired: type={trigger_type.value}, "
            f"count_today={self._trigger_count_today}"
        )

        # Notify callbacks
        for callback in self._on_trigger:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Trigger callback error: {e}")

    # === Manual triggers ===

    async def trigger_manually(self, topic: str = "") -> TriggerEvent:
        """Fire a manual trigger (from UI or API)."""
        event = TriggerEvent(
            trigger_type=TriggerType.MANUAL,
            fired_at=datetime.now(),
            topic=topic,
        )

        for callback in self._on_trigger:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Manual trigger callback error: {e}")

        return event

    # === Activity tracking ===

    def record_user_activity(self):
        """Record that the user was active (spoke or interacted)."""
        self._last_user_activity = datetime.now()

    # === Helpers ===

    def _is_active_hours(self) -> bool:
        """Check if current time is within configured active hours."""
        now = datetime.now().hour
        return self.config.active_start_hour <= now < self.config.active_end_hour

    def is_active(self) -> bool:
        """Check if the scheduler is within active hours and enabled."""
        return self._running and self.config.enabled and self._is_active_hours()

    @property
    def time_until_next_trigger(self) -> float | None:
        """Seconds until next trigger, or None if not scheduled."""
        if self._next_trigger_time is None:
            return None
        delta = (self._next_trigger_time - datetime.now()).total_seconds()
        return max(0, delta)

    @property
    def trigger_count_today(self) -> int:
        return self._trigger_count_today

    def reset_daily_count(self):
        """Reset the daily trigger counter (call at midnight)."""
        self._trigger_count_today = 0

    def set_enabled(self, enabled: bool):
        """Enable or disable spontaneous triggers."""
        self.config.enabled = enabled
        if not enabled and self._running:
            logger.info("Spontaneous mode disabled")
        elif enabled and not self._running:
            logger.info("Spontaneous mode enabled — restart agent to apply")
