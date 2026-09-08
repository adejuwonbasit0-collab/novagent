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
    # See os_control/windows.py's top-of-file comment for the underlying
    # bug this addresses: type_text fires into whatever currently has
    # focus, with no idea what "the app just opened" is, so a command
    # sequence like open_application -> type_text can race a slow-starting
    # app. Windows gets a real signal (poll the foreground window handle
    # until it changes); doing the same properly on macOS means polling
    # NSWorkspace.frontmostApplication via pyobjc, which isn't a current
    # dependency of this project. A fixed settle delay is a strictly
    # weaker mitigation -- it doesn't confirm anything actually changed --
    # but it's honest about that limitation rather than pretending to
    # verify what it can't. Real fix: add pyobjc and poll frontmost app.
    _APP_LAUNCH_SETTLE_S = 0.8

    def open_application(self, app_name: str) -> OSActionResult:
        try:
            subprocess.run(["open", "-a", app_name], check=True)
            import time

            time.sleep(self._APP_LAUNCH_SETTLE_S)
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

    def create_file(self, path: str, content: str = "") -> OSActionResult:
        try:
            full_path = os.path.expanduser(path)
            if os.path.exists(full_path):
                return OSActionResult(
                    success=False, message="", error=f"A file already exists at {path} -- not overwriting it."
                )
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return OSActionResult(success=True, message=f"Created {path}")
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

    def get_active_window(self) -> OSActionResult:
        try:
            script = (
                'tell application "System Events"\n'
                "set frontApp to first application process whose frontmost is true\n"
                "set appName to name of frontApp\n"
                "try\n"
                "set winName to name of first window of frontApp\n"
                "on error\n"
                'set winName to "(no window title)"\n'
                "end try\n"
                "return appName & \"|||\" & winName\n"
                "end tell"
            )
            result = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
            app_name, _, window_title = result.stdout.strip().partition("|||")
            return OSActionResult(success=True, message=f'{app_name} — "{window_title}"')
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def read_file(self, path: str, max_chars: int = 20000) -> OSActionResult:
        try:
            full_path = os.path.expanduser(os.path.expandvars(path))
            if not os.path.isfile(full_path):
                return OSActionResult(success=False, message="", error=f"No file at {path}")
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars + 1)
            truncated = len(content) > max_chars
            if truncated:
                content = content[:max_chars]
            note = f"\n\n[... truncated, file continues past {max_chars} characters]" if truncated else ""
            return OSActionResult(success=True, message=content + note)
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))
