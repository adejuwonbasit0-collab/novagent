from __future__ import annotations

import shutil
import subprocess
import webbrowser
import os

from os_control.base import OSActionResult, OSController


class LinuxController(OSController):
    def open_application(self, app_name: str) -> OSActionResult:
        try:
            subprocess.Popen([app_name])
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
