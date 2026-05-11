"""
Progress report UI for the English Coach Agent.
Generates and displays weekly progress reports with metrics and recommendations.
Viewable from the system tray menu.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.theme import AppTheme
from config.logging_config import setup_logging

logger = setup_logging()


class ProgressReport(ctk.CTkToplevel):
    """Progress report window showing weekly metrics and insights."""

    def __init__(self, parent, session_manager=None, corrections_tracker=None):
        super().__init__(parent)

        self._session_manager = session_manager
        self._corrections_tracker = corrections_tracker

        self.title("Progress Report — English Coach Agent")
        self.geometry("520x620")
        self.resizable(False, False)

        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 520) // 2
        y = parent_y + (parent_h - 620) // 2
        self.geometry(f"+{x}+{y}")
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_report()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=AppTheme.BG_DARKER)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="  Weekly Progress Report",
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY,
        ).pack(side="left", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD)

        ctk.CTkButton(
            header, text="Close", width=60, height=24,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_SMALL),
            fg_color=AppTheme.BG_CARD, command=self.destroy,
        ).pack(side="right", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD)

        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)

        # Session stats
        self._add_section(content, " Practice Summary")
        self._summary_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._summary_frame.pack(fill="x", padx=AppTheme.PADDING_MD)

        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # Trend
        self._add_section(content, " Trends")
        self._trend_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._trend_frame.pack(fill="x", padx=AppTheme.PADDING_MD)

        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # Error breakdown
        self._add_section(content, " Error Categories")
        self._error_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._error_frame.pack(fill="x", padx=AppTheme.PADDING_MD)

        ctk.CTkFrame(content, height=1, fg_color=AppTheme.BG_CARD).pack(
            fill="x", padx=AppTheme.PADDING_MD, pady=AppTheme.PADDING_MD
        )

        # Recommendations
        self._add_section(content, " Recommendations")
        self._rec_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._rec_frame.pack(fill="x", padx=AppTheme.PADDING_MD)

        # Export button
        ctk.CTkButton(
            self, text="Export as Text", width=140, height=28,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            fg_color=AppTheme.BG_CARD, command=self._export_text,
        ).pack(pady=AppTheme.PADDING_MD)

    def _add_section(self, parent, title: str):
        ctk.CTkLabel(
            parent,
            text=title,
            font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_HEADING, "bold"),
            text_color=AppTheme.TEXT_PRIMARY, anchor="w",
        ).pack(fill="x", padx=AppTheme.PADDING_MD, pady=(AppTheme.PADDING_MD, AppTheme.PADDING_SM))

    def _add_stat_row(self, parent, label: str, value: str, color: str = AppTheme.TEXT_SECONDARY):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)

        ctk.CTkLabel(
            row, text=label, font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
            text_color=AppTheme.TEXT_SECONDARY, anchor="w",
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            row, text=str(value),
            font=(AppTheme.FONT_MONO, AppTheme.FONT_SIZE_BODY, "bold"),
            text_color=color,
        ).pack(side="right", padx=5)

    def _load_report(self):
        asyncio.create_task(self._load_report_async())

    async def _load_report_async(self):
        try:
            if self._session_manager:
                weekly = await self._session_manager.get_weekly_stats()
                total = await self._session_manager.get_total_stats()
                streak = await self._session_manager.get_streak_days()

                # Clear previous
                for w in self._summary_frame.winfo_children():
                    w.destroy()

                self._add_stat_row(self._summary_frame, "Sessions this week:", weekly.get("session_count", 0))
                self._add_stat_row(self._summary_frame, "Total time:", f"{weekly.get('total_minutes', 0)} min")
                self._add_stat_row(self._summary_frame, "Conversation turns:", weekly.get("total_turns", 0))
                self._add_stat_row(self._summary_frame, "Corrections:", weekly.get("total_corrections", 0),
                                   AppTheme.TEXT_CORRECTION)

                # Streak
                for w in self._trend_frame.winfo_children():
                    w.destroy()

                self._add_stat_row(self._trend_frame, "Practice streak:", f"{streak} days",
                                   AppTheme.ACCENT_SUCCESS if streak >= 3 else AppTheme.TEXT_SECONDARY)
                self._add_stat_row(self._trend_frame, "All-time sessions:", total.get("total_sessions", 0))
                self._add_stat_row(self._trend_frame, "All-time hours:", total.get("total_hours", 0))
                self._add_stat_row(self._trend_frame, "Avg session:", f"{total.get('avg_session_minutes', 0)} min")

            # Error breakdown
            if self._corrections_tracker:
                for w in self._error_frame.winfo_children():
                    w.destroy()

                errors = await self._corrections_tracker.get_frequent_errors(limit=5, days=7)
                if errors:
                    for cat, count in errors:
                        self._add_stat_row(self._error_frame, cat, count, AppTheme.TEXT_CORRECTION)
                else:
                    ctk.CTkLabel(
                        self._error_frame,
                        text="No errors recorded this week",
                        font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
                        text_color=AppTheme.TEXT_MUTED,
                    ).pack(pady=AppTheme.PADDING_SM)

            # Recommendations
            for w in self._rec_frame.winfo_children():
                w.destroy()

            recs = self._generate_recommendations(streak, weekly)
            for rec in recs:
                ctk.CTkLabel(
                    self._rec_frame,
                    text=f"  {rec}",
                    font=(AppTheme.FONT_FAMILY, AppTheme.FONT_SIZE_BODY),
                    text_color=AppTheme.TEXT_SECONDARY,
                    anchor="w", wraplength=460,
                ).pack(fill="x", pady=2)

        except Exception as e:
            logger.warning(f"Error loading report: {e}")

    def _generate_recommendations(self, streak: int, weekly: dict) -> list[str]:
        recs = []
        sessions = weekly.get("session_count", 0)
        corrections = weekly.get("total_corrections", 0)
        minutes = weekly.get("total_minutes", 0)

        if sessions < 3:
            recs.append("Aim for 3+ sessions per week for consistent progress.")
        if minutes > 0 and sessions > 0 and (minutes / sessions) < 10:
            recs.append("Try extending sessions to at least 15 minutes for deeper practice.")
        if streak >= 5:
            recs.append(f"Great job! {streak}-day streak. Keep it going!")
        elif streak >= 2:
            recs.append(f"You're on a roll — {streak} days in a row!")
        else:
            recs.append("Start a streak — practice at least once today!")
        if corrections > 0 and corrections > sessions * 5:
            recs.append("Focus on quality over quantity — slow down and think before speaking.")
        if not recs:
            recs.append("Keep up the consistent practice! You're making progress.")

        return recs

    def _export_text(self):
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile=f"progress_report_{datetime.now().strftime('%Y%m%d')}.txt",
        )
        if filepath:
            asyncio.create_task(self._export_async(filepath))

    async def _export_async(self, filepath: str):
        try:
            from scripts.export_corrections import print_summary
            import io

            # Capture the summary output
            report_lines = [f"English Coach Agent — Progress Report",
                          f"Generated: {datetime.now().isoformat()}",
                          f"", ""]

            if self._session_manager:
                weekly = await self._session_manager.get_weekly_stats()
                total = await self._session_manager.get_total_stats()
                streak = await self._session_manager.get_streak_days()

                report_lines.extend([
                    f"Sessions: {weekly.get('session_count', 0)}",
                    f"Total time: {weekly.get('total_minutes', 0)} min",
                    f"Corrections: {weekly.get('total_corrections', 0)}",
                    f"Streak: {streak} days",
                    f"All-time sessions: {total.get('total_sessions', 0)}",
                    f"All-time hours: {total.get('total_hours', 0)}",
                ])

            Path(filepath).write_text("\n".join(report_lines), encoding="utf-8")
            logger.info(f"Report exported to: {filepath}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
