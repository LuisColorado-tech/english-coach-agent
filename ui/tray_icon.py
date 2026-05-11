"""
System tray icon for the English Coach Agent.
Shows in Windows notification area. Keeps agent running when window is minimized.
Provides quick-access menu: open panel, pause/resume, stats, quit.
"""

import asyncio
import threading
from pathlib import Path

from config.logging_config import setup_logging

logger = setup_logging()


class TrayIcon:
    """
    System tray icon using pystray.
    Runs on a separate thread since pystray uses its own event loop.
    """

    def __init__(self, main_window, agent=None):
        self._main_window = main_window
        self._agent = agent
        self._icon = None
        self._tray_thread: threading.Thread | None = None
        self._running = False
        self._paused = False
        self._corrections_today = 0

        # Icon paths
        self._project_root = Path(__file__).parent.parent
        self._icon_path = self._project_root / "assets" / "icon.ico"

        # Ensure icon exists
        self._ensure_icon()

    def _ensure_icon(self):
        """Generate a fallback icon if icon.ico doesn't exist."""
        if self._icon_path.exists():
            return

        try:
            self._generate_icon()
        except Exception as e:
            logger.warning(f"Could not generate icon: {e}")

    def _generate_icon(self):
        """Generate a simple icon using Pillow."""
        from PIL import Image, ImageDraw

        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background circle
        draw.ellipse([4, 4, size - 4, size - 4], fill=(52, 152, 219, 255))

        # Simple speech bubble shape
        draw.rectangle([16, 22, 48, 44], fill=(255, 255, 255, 255))
        draw.polygon(
            [(24, 44), (20, 52), (32, 44)],
            fill=(255, 255, 255, 255),
        )

        # Ensure directory exists
        self._icon_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(self._icon_path), format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
        logger.info(f"Generated tray icon: {self._icon_path}")

    def start(self):
        """Start the tray icon on a separate thread."""
        if self._running:
            return

        self._running = True
        self._tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        self._tray_thread.start()
        logger.info("System tray icon started")

    def stop(self):
        """Stop the tray icon and clean up."""
        self._running = False
        if self._icon:
            self._icon.stop()
            self._icon = None
        logger.info("System tray icon stopped")

    def _run_tray(self):
        """Run the pystray icon in its own thread."""
        try:
            import pystray
            from PIL import Image

            # Load icon image
            icon_image = Image.open(str(self._icon_path))

            # Build menu
            menu = self._build_menu()

            # Create icon
            self._icon = pystray.Icon(
                "english_coach_agent",
                icon_image,
                "English Coach Agent",
                menu=menu,
            )

            # Set up double-click handler
            self._icon.on_activate = self._on_activate

            # Run the tray (blocks this thread)
            self._icon.run()

        except ImportError:
            logger.warning(
                "pystray not installed. System tray unavailable. "
                "Install with: pip install pystray"
            )
        except Exception as e:
            logger.error(f"Tray icon error: {e}")

    def _build_menu(self):
        """Build the tray context menu."""
        try:
            import pystray

            def open_panel(*args):
                self._restore_window()

            def toggle_pause(*args):
                self._toggle_pause()

            def show_stats(*args):
                self._show_stats_window()

            def show_corrections(*args):
                self._show_corrections()

            def run_setup(*args):
                self._run_setup()

            def quit_app(*args):
                self._quit_app()

            return pystray.Menu(
                pystray.MenuItem("Open Panel", open_panel, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Pause / Resume", toggle_pause),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    f"Corrections today: {self._corrections_today}",
                    show_corrections,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Settings", run_setup),
                pystray.MenuItem("Quit", quit_app),
            )
        except Exception as e:
            logger.error(f"Failed to build tray menu: {e}")
            return None

    def _on_activate(self, icon, button, time):
        """Handle activation: left click = open, double click = open."""
        self._restore_window()

    def _restore_window(self):
        """Restore and show the main window."""
        if self._main_window:
            self._main_window.restore_from_tray()

    def _toggle_pause(self):
        """Toggle agent pause state."""
        if self._agent:
            if self._paused:
                self._agent.resume()
                self._paused = False
            else:
                self._agent.pause()
                self._paused = True

            # Update menu text
            self._update_menu()

    def _show_stats_window(self):
        """Show the statistics popup."""
        self._restore_window()
        if self._main_window:
            from ui.stats_panel import StatsPanel
            try:
                StatsPanel(
                    self._main_window.root,
                    session_manager=getattr(self._agent, '_session_manager', None),
                    corrections_tracker=getattr(self._agent, '_corrections_tracker', None),
                )
            except Exception as e:
                logger.warning(f"Could not show stats: {e}")

    def _show_corrections(self):
        """Show correction count info."""
        self._restore_window()

    def _run_setup(self):
        """Run the setup wizard."""
        from ui.setup_wizard import run_setup_wizard
        threading.Thread(target=run_setup_wizard, daemon=True).start()

    def _quit_app(self):
        """Fully close the application."""
        self._running = False

        if self._agent:
            # Schedule async stop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._agent.stop())
                else:
                    asyncio.run(self._agent.stop())
            except Exception:
                pass

        if self._main_window:
            self._main_window.quit()

        if self._icon:
            self._icon.stop()

    def _update_menu(self):
        """Rebuild and update the tray menu."""
        if self._icon:
            self._icon.menu = self._build_menu()

    def update_correction_count(self, count: int):
        """Update the correction counter in the tray menu."""
        self._corrections_today = count
        self._update_menu()

    def update_state(self, state_name: str):
        """Update icon tooltip with current state."""
        if self._icon:
            state_labels = {
                "IDLE": "Idle",
                "LISTENING": "Listening...",
                "THINKING": "Thinking...",
                "SPEAKING": "Speaking...",
                "PAUSED": "Paused",
            }
            label = state_labels.get(state_name.upper(), state_name)
            self._icon.title = f"English Coach — {label}"

    @property
    def is_running(self) -> bool:
        return self._running
