from __future__ import annotations

import shutil
import subprocess
import webbrowser
import os

from os_control.base import OSActionResult, OSController


class LinuxController(OSController):
    # See os_control/windows.py's top-of-file comment. Real focus
    # verification on Linux would need xdotool (or a similar tool) and
    # varies by desktop environment/X11 vs Wayland -- not a current
    # dependency. Same honestly-weaker fixed-delay mitigation as macOS.
    _APP_LAUNCH_SETTLE_S = 0.8

    def open_application(self, app_name: str) -> OSActionResult:
        try:
            subprocess.Popen([app_name])
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
            opener = "xdg-open" if shutil.which("xdg-open") else "nautilus"
            subprocess.run([opener, path], check=True)
            return OSActionResult(success=True, message=f"Opened folder {path}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def lock_computer(self) -> OSActionResult:
        for cmd in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=True)
                    return OSActionResult(success=True, message="Locked")
                except Exception as e:
                    return OSActionResult(success=False, message="", error=str(e))
        return OSActionResult(success=False, message="", error="No supported lock command found")

    def shutdown_computer(self) -> OSActionResult:
        try:
            subprocess.run(["systemctl", "poweroff"], check=True)
            return OSActionResult(success=True, message="Shutting down")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def restart_computer(self) -> OSActionResult:
        try:
            subprocess.run(["systemctl", "reboot"], check=True)
            return OSActionResult(success=True, message="Restarting")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def send_notification(self, title: str, message: str) -> OSActionResult:
        try:
            subprocess.run(["notify-send", title, message], check=True)
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
            if not shutil.which("xdotool"):
                raise FileNotFoundError("xdotool is required for typing")
            subprocess.run(["xdotool", "type", "--delay", "10", text], check=True)
            return OSActionResult(success=True, message="Typed the requested text")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def open_folder_in_application(self, path: str, app_name: str) -> OSActionResult:
        try:
            subprocess.Popen([app_name, path])
            return OSActionResult(success=True, message=f"Opened {path} in {app_name}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def get_active_window(self) -> OSActionResult:
        try:
            # Same xdotool dependency as type_text above -- X11 only. Wayland
            # has no equivalent cross-desktop-environment API; this fails
            # with a clear reason there rather than silently returning
            # nothing, per spec section 47 (don't fake a feature that isn't
            # actually available).
            if not shutil.which("xdotool"):
                raise FileNotFoundError("xdotool is required to read the active window (X11 only)")
            title = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"], check=True, capture_output=True, text=True
            ).stdout.strip()
            window_id = subprocess.run(
                ["xdotool", "getactivewindow"], check=True, capture_output=True, text=True
            ).stdout.strip()
            pid_result = subprocess.run(
                ["xdotool", "getwindowpid", window_id], capture_output=True, text=True
            )
            process_name = "unknown process"
            if pid_result.returncode == 0 and pid_result.stdout.strip():
                try:
                    with open(f"/proc/{pid_result.stdout.strip()}/comm") as f:
                        process_name = f.read().strip()
                except OSError:
                    pass
            return OSActionResult(success=True, message=f'{process_name} — "{title}"')
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
