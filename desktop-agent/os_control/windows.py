from __future__ import annotations

import os
import subprocess
import webbrowser
import shutil

from os_control.base import OSActionResult, OSController


class WindowsController(OSController):
    def open_application(self, app_name: str) -> OSActionResult:
        try:
            aliases = {
                "chrome": "chrome.exe",
                "google chrome": "chrome.exe",
                "notepad": "notepad.exe",
                "settings": "ms-settings:",
                "control panel": "control.exe",
            }
            os.startfile(aliases.get(app_name.lower().strip(), app_name))  # type: ignore[attr-defined]
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
            os.startfile(path)  # type: ignore[attr-defined]
            return OSActionResult(success=True, message=f"Opened folder {path}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def lock_computer(self) -> OSActionResult:
        try:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            return OSActionResult(success=True, message="Locked")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def shutdown_computer(self) -> OSActionResult:
        try:
            subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
            return OSActionResult(success=True, message="Shutting down in 5 seconds")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def restart_computer(self) -> OSActionResult:
        try:
            subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
            return OSActionResult(success=True, message="Restarting in 5 seconds")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def send_notification(self, title: str, message: str) -> OSActionResult:
        try:
            # win10toast/plyer are the common choices; kept as a soft dependency
            # so the agent still runs without it — swap in real notifications
            # once the notification-provider decision is made.
            from plyer import notification

            notification.notify(title=title, message=message, app_name="Nova")
            return OSActionResult(success=True, message="Notified")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def create_folder(self, path: str) -> OSActionResult:
        try:
            os.makedirs(os.path.expandvars(os.path.expanduser(path)), exist_ok=True)
            return OSActionResult(success=True, message=f"Created folder {path}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def type_text(self, text: str) -> OSActionResult:
        try:
            import pyautogui

            pyautogui.write(text, interval=0.01)
            return OSActionResult(success=True, message="Typed the requested text")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def open_folder_in_application(self, path: str, app_name: str) -> OSActionResult:
        try:
            aliases = {"visual studio code": "code", "vs code": "code", "vscode": "code"}
            executable = aliases.get(app_name.lower().strip(), app_name)
            command = shutil.which(executable)
            if command:
                subprocess.Popen([command, os.path.expandvars(os.path.expanduser(path))])
            elif executable == "code":
                candidates = [
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\bin\code.cmd"),
                ]
                candidate = next((item for item in candidates if os.path.exists(item)), None)
                if not candidate:
                    raise FileNotFoundError("VS Code command 'code' was not found")
                # NEVER shell=True here: `path` is a model/user-controlled
                # string. With shell=True on Windows the argument list is
                # rejoined into a single command line and handed to cmd.exe,
                # so a path containing shell metacharacters (e.g. `& calc.exe`,
                # `& del /f /q C:\*`) would execute as a second command. The
                # list form without shell=True passes argv directly to
                # CreateProcess with no shell involved, so metacharacters in
                # the path are inert.
                subprocess.Popen([candidate, os.path.expandvars(os.path.expanduser(path))])
            else:
                raise FileNotFoundError(f"Application not found: {app_name}")
            return OSActionResult(success=True, message=f"Opened {path} in {app_name}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))
