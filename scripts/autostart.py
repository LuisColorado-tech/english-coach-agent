#!/usr/bin/env python3
"""
Windows autostart manager for the English Coach Agent.
Adds/removes the agent from Windows startup via registry or Startup folder.
"""

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
RUN_CMD = f'"{sys.executable}" "{PROJECT_ROOT / "run.py"}"'
APP_NAME = "English Coach Agent"


def get_startup_folder() -> Path:
    """Get the Windows Startup folder path."""
    if sys.platform != "win32":
        print("Autostart only supported on Windows.")
        return None

    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        startup_path, _ = winreg.QueryValueEx(key, "Startup")
        winreg.CloseKey(key)
        return Path(startup_path)
    except Exception:
        # Fallback to common path
        home = Path.home()
        return home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def create_shortcut(target_path: Path, shortcut_path: Path, arguments: str = ""):
    """Create a Windows shortcut (.lnk) file."""
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(target_path)
        shortcut.Arguments = arguments
        shortcut.WorkingDirectory = str(PROJECT_ROOT)
        shortcut.Description = APP_NAME
        shortcut.IconLocation = str(PROJECT_ROOT / "assets" / "icon.ico")
        shortcut.Save()

        pythoncom.CoUninitialize()
    except ImportError:
        print("WARNING: pywin32 not installed. Using registry method instead.")
        _registry_install()
    except Exception as e:
        print(f"ERROR creating shortcut: {e}")
        print("Trying registry fallback...")
        _registry_install()


def _registry_install():
    """Install autostart via Windows registry."""
    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )

        # Run via batch file for proper working directory
        bat_path = PROJECT_ROOT / "run.bat"
        if bat_path.exists():
            command = f'"{bat_path}"'
        else:
            command = f'"{sys.executable}" "{PROJECT_ROOT / "run.py"}" --gui'

        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        print("Autostart enabled (registry)")
    except Exception as e:
        print(f"ERROR: Could not set registry autostart: {e}")


def _registry_remove():
    """Remove autostart from Windows registry."""
    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("Autostart disabled (registry)")
    except FileNotFoundError:
        print("Autostart was not enabled (registry)")
    except Exception as e:
        print(f"ERROR removing registry autostart: {e}")


def install():
    """Install the agent to start automatically with Windows."""
    if sys.platform != "win32":
        print("ERROR: Autostart only supported on Windows.")
        print("On Linux, use systemd or .config/autostart/")
        return False

    startup_folder = get_startup_folder()
    if startup_folder is None:
        return False

    # Try shortcut method first
    try:
        # Create a VBS wrapper to run without console window
        vbs_path = PROJECT_ROOT / "run_hidden.vbs"
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "{PROJECT_ROOT / "run.bat"}", 0, False
'''
        vbs_path.write_text(vbs_content)

        shortcut_path = startup_folder / f"{APP_NAME}.lnk"
        python_exe = sys.executable
        create_shortcut(
            python_exe,
            shortcut_path,
            arguments=f'"{PROJECT_ROOT / "run.py"}" --gui',
        )
        print(f"Autostart enabled: {shortcut_path}")
        return True
    except Exception as e:
        print(f"Shortcut method failed: {e}")

    # Fallback to registry
    _registry_install()
    return True


def uninstall():
    """Remove the agent from Windows startup."""
    if sys.platform != "win32":
        print("ERROR: Autostart only supported on Windows.")
        return False

    startup_folder = get_startup_folder()
    if startup_folder:
        shortcut_path = startup_folder / f"{APP_NAME}.lnk"
        if shortcut_path.exists():
            shortcut_path.unlink()
            print(f"Removed shortcut: {shortcut_path}")

    _registry_remove()

    # Remove VBS helper
    vbs_path = PROJECT_ROOT / "run_hidden.vbs"
    if vbs_path.exists():
        vbs_path.unlink()

    return True


def is_installed() -> bool:
    """Check if autostart is currently enabled."""
    if sys.platform != "win32":
        return False

    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
    except Exception:
        pass

    # Check Startup folder
    startup_folder = get_startup_folder()
    if startup_folder:
        shortcut = startup_folder / f"{APP_NAME}.lnk"
        return shortcut.exists()

    return False


def toggle():
    """Toggle autostart on/off."""
    if is_installed():
        uninstall()
    else:
        install()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage Windows autostart for English Coach Agent")
    parser.add_argument("action", nargs="?", choices=["install", "uninstall", "status", "toggle"],
                        default="status", help="Action to perform")
    args = parser.parse_args()

    if args.action == "install":
        install()
    elif args.action == "uninstall":
        uninstall()
    elif args.action == "status":
        if is_installed():
            print("Autostart is ENABLED")
        else:
            print("Autostart is DISABLED")
    elif args.action == "toggle":
        toggle()
