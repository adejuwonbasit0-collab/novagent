from __future__ import annotations

import subprocess
import webbrowser
import os

from os_control.base import OSActionResult, OSController


def _applescript_string(value: str) -> str:
    """Escape a Python string for safe interpolation inside a double-quoted
    AppleScript string literal. Without this, a value like
    `foo" & do shell script "rm -rf ~" & "` breaks out of the literal and
    runs arbitrary shell commands via `do shell script`."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class MacOSController(OSController):
    def open_application(self, app_name: str) -> OSActionResult:
        try:
            subprocess.run(["open", "-a", app_name], check=True)
            return OSActionResult(success=True, message=f"Opened {app_name}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def open_url(self, url: str) -> OSActionResult:
        try:
            webbrowser.open(url)
            return OSActionResult(success=True, message=f"Opened {url}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def open_folder(self, path: str) -> OSActionResult:
        try:
            subprocess.run(["open", path], check=True)
            return OSActionResult(success=True, message=f"Opened folder {path}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def lock_computer(self) -> OSActionResult:
        try:
            subprocess.run(
                ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                check=True,
            )
            return OSActionResult(success=True, message="Locked")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def shutdown_computer(self) -> OSActionResult:
        try:
            subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'], check=True)
            return OSActionResult(success=True, message="Shutting down")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def restart_computer(self) -> OSActionResult:
        try:
            subprocess.run(["osascript", "-e", 'tell app "System Events" to restart'], check=True)
            return OSActionResult(success=True, message="Restarting")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def send_notification(self, title: str, message: str) -> OSActionResult:
        try:
            script = f"display notification {_applescript_string(message)} with title {_applescript_string(title)}"
            subprocess.run(["osascript", "-e", script], check=True)
            return OSActionResult(success=True, message="Notified")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def create_folder(self, path: str) -> OSActionResult:
        try:
            os.makedirs(os.path.expanduser(path), exist_ok=True)
            return OSActionResult(success=True, message=f"Created folder {path}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def type_text(self, text: str) -> OSActionResult:
        try:
            script = f"tell application \"System Events\" to keystroke {_applescript_string(text)}"
            subprocess.run(["osascript", "-e", script], check=True)
            return OSActionResult(success=True, message="Typed the requested text")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def open_folder_in_application(self, path: str, app_name: str) -> OSActionResult:
        try:
            subprocess.run(["open", "-a", app_name, path], check=True)
            return OSActionResult(success=True, message=f"Opened {path} in {app_name}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))
