"""
Statistics panel for the English Coach Agent.
Shows session and historical progress metrics.
"""

import asyncio
from datetime import datetime

import customtkinter as ctk

from ui.theme import AppTheme


class StatsPanel(ctk.CTkToplevel):
    """
    Standalone statistics window.
    Shows real-time session stats and historical progress from SQLite.
    """

    def __init__(self, parent, session_manager=None, corrections_tracker=None):
        super().__init__(parent)

        self._session_manager = session_manager
        self._corrections_tracker = corrections_tracker

        self.title("Statistics — English Coach Agent")
        self.geometry("450x550")
        self.resizable(False, False)

        # Center on parent
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 450) // 2
        y = parent_y + (parent_h - 550) // 2
        self.geometry(f"+{x}+{y}")

        # Make transient (stays on top of parent)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Load data
        self._load_stats()

        # Auto-refresh every 30 seconds
        self._auto_refresh()

    def _build_ui(self):
        """Build the stats panel UI."""
        # Header
        header = ctk.CTkFrame(self, fg_color=AppTheme.BG_DARKER)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="  Progress & Statistics",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
        ).pack(side="left", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD)

        # Close button
        ctk.CTkButton(
            header,
            text="Close",
            width=60,
            height=24,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.BG_CARD,
            command=self.destroy,
        ).pack(side="right", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD)

        # Scrollable content
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # === This Week ===
        section = self._add_section(content, "This Week")

        self._this_week_sessions = ctk.CTkLabel(
            content, text="Sessions: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._this_week_sessions.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._this_week_minutes = ctk.CTkLabel(
            content, text="Minutes practiced: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._this_week_minutes.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._this_week_corrections = ctk.CTkLabel(
            content, text="Corrections: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_CORRECTION, anchor="w",
        )
        self._this_week_corrections.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._this_week_turns = ctk.CTkLabel(
            content, text="Conversation turns: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._this_week_turns.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._this_week_error = ctk.CTkLabel(
            content, text="Most frequent error: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_MUTED, anchor="w",
        )
        self._this_week_error.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        # Separator
        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # === Streak ===
        section = self._add_section(content, "Your Streak")

        self._streak_label = ctk.CTkLabel(
            content,
            text="—",
            font=(AppTheme.FONT_FAMILY, 28, "bold"),
            text_color=AppTheme.ACCENT_SUCCESS,
        )
        self._streak_label.pack(pady=(AppTheme.PADDING_SM, AppTheme.PADDING_SM))

        ctk.CTkLabel(
            content,
            text="consecutive days",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY,
        ).pack(pady=(0, AppTheme.PADDING_SM))

        # Separator
        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # === All Time ===
        section = self._add_section(content, "All Time")

        self._total_sessions = ctk.CTkLabel(
            content, text="Total sessions: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._total_sessions.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._total_hours = ctk.CTkLabel(
            content, text="Total hours: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._total_hours.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._total_corrections = ctk.CTkLabel(
            content, text="Total corrections: —",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_CORRECTION, anchor="w",
        )
        self._total_corrections.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        self._avg_session = ctk.CTkLabel(
            content, text="Avg session: — min",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        )
        self._avg_session.pack(fill="x", padx=AppTheme.PADDING_XL, pady=2)

        # Separator
        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # === Error Breakdown ===
        section = self._add_section(content, "Error Categories (Last 7 Days)")

        self._error_list = ctk.CTkFrame(content, fg_color="transparent")
        self._error_list.pack(fill="x", padx=AppTheme.PADDING_XL, pady=(0, AppTheme.PADDING_MD))

        # Refresh button
        ctk.CTkButton(
            self,
            text="Refresh Stats",
            width=120,
            height=28,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            fg_color=AppTheme.BG_CARD,
            command=self._load_stats,
        ).pack(pady=AppTheme.PADDING_MD)

    def _add_section(self, parent, title: str) -> ctk.CTkLabel:
        """Add a section header."""
        return ctk.CTkLabel(
            parent,
            text=title,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x", padx=AppTheme.PADDING_MD, pady=(AppTheme.PADDING_MD, AppTheme.PADDING_SM))

    def _load_stats(self):
        """Load and display stats from database."""
        if self._session_manager:
            asyncio.create_task(self._load_stats_async())

    async def _load_stats_async(self):
        """Async load stats from session manager and corrections tracker."""
        try:
            if self._session_manager:
                weekly = await self._session_manager.get_weekly_stats()
                total = await self._session_manager.get_total_stats()
                streak = await self._session_manager.get_streak_days()

                # Update weekly stats
                self._this_week_sessions.configure(
                    text=f"Sessions: {weekly.get('session_count', 0)}"
                )
                self._this_week_minutes.configure(
                    text=f"Minutes practiced: {weekly.get('total_minutes', 0)}"
                )
                self._this_week_corrections.configure(
                    text=f"Corrections: {weekly.get('total_corrections', 0)}"
                )
                self._this_week_turns.configure(
                    text=f"Conversation turns: {weekly.get('total_turns', 0)}"
                )

                # Update streak
                self._streak_label.configure(text=str(streak))

                # Update all-time
                self._total_sessions.configure(
                    text=f"Total sessions: {total.get('total_sessions', 0)}"
                )
                self._total_hours.configure(
                    text=f"Total hours: {total.get('total_hours', 0)}"
                )
                self._total_corrections.configure(
                    text=f"Total corrections: {total.get('total_corrections', 0)}"
                )
                self._avg_session.configure(
                    text=f"Avg session: {total.get('avg_session_minutes', 0)} min"
                )

            # Load error breakdown
            if self._corrections_tracker:
                progress = await self._corrections_tracker.get_progress_stats(days=7)

                self._this_week_error.configure(
                    text=f"Most frequent error: {progress.get('most_frequent_category', 'none')}"
                )

                # Display error categories
                errors = await self._corrections_tracker.get_frequent_errors(limit=5, days=7)

                for widget in self._error_list.winfo_children():
                    widget.destroy()

                if errors:
                    for category, count in errors:
                        bar_frame = ctk.CTkFrame(self._error_list, fg_color="transparent")
                        bar_frame.pack(fill="x", pady=1)

                        ctk.CTkLabel(
                            bar_frame,
                            text=f"{category}",
                            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
                            text_color=AppTheme.TEXT_SECONDARY,
                            width=150, anchor="w",
                        ).pack(side="left")

                        ctk.CTkLabel(
                            bar_frame,
                            text=f"{count}",
                            font=(AppTheme.FONT_MONO, AppTheme.FONT_SIZE_BODY, "bold"),
                            text_color=AppTheme.ACCENT_PRIMARY,
                        ).pack(side="right")
                else:
                    ctk.CTkLabel(
                        self._error_list,
                        text="No errors recorded yet",
                        font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
                        text_color=AppTheme.TEXT_MUTED,
                    ).pack()

        except Exception as e:
            pass  # Stats loading failure shouldn't break UI

    def _auto_refresh(self):
        """Auto-refresh stats periodically."""
        self._load_stats()
        self.after(30000, self._auto_refresh)  # Refresh every 30 seconds

    def set_managers(self, session_manager, corrections_tracker):
        """Set database managers for stats queries."""
        self._session_manager = session_manager
        self._corrections_tracker = corrections_tracker
        self._load_stats()
