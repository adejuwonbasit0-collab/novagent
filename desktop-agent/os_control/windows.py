from __future__ import annotations

import os
import subprocess
import webbrowser
import shutil
import time

from os_control.base import OSActionResult, OSController

# Real bug found on audit: open_application returned success the instant
# os.startfile() was called, with no wait for the new window to actually
# exist and take focus. type_text (pyautogui.write) types into whatever
# window currently has OS focus at the moment it runs -- it has no idea
# what "the app we just opened" even is. The orchestrator awaits
# open_application's response before sending type_text, so the network
# round-trip is properly sequenced, but that response was meaningless: it
# only confirmed the OS accepted the launch request, not that the app's
# window exists yet. Cold-starting an app (Notepad from a fresh process,
# and especially anything heavier) can easily take longer than the gap
# between the two commands, so type_text fires into whatever WAS focused
# before -- which reads as "Nova did nothing," since nothing visibly
# happens in the window the user is looking at.
#
# Fixed by polling the actual Win32 foreground window handle after
# launching, and only returning success once it has changed (a new window
# took focus) or a bounded timeout elapses. This is still a heuristic --
# it confirms *some* new window took focus, not specifically that it
# belongs to the app that was just launched (a notification popping up at
# the same moment would also count) -- but it's a real signal instead of
# none, and closes the common case this bug was reported against.
_FOREGROUND_POLL_TIMEOUT_S = 4.0
_FOREGROUND_POLL_INTERVAL_S = 0.1


def _get_foreground_window():
    try:
        import ctypes

        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def _wait_for_new_foreground_window(previous_hwnd) -> None:
    if previous_hwnd is None:
        # ctypes/user32 unavailable for some reason -- fall back to a fixed
        # settle delay rather than returning with no wait at all.
        time.sleep(0.6)
        return
    deadline = time.monotonic() + _FOREGROUND_POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        if _get_foreground_window() != previous_hwnd:
            return
        time.sleep(_FOREGROUND_POLL_INTERVAL_S)


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
            previous_hwnd = _get_foreground_window()
            os.startfile(aliases.get(app_name.lower().strip(), app_name))  # type: ignore[attr-defined]
            _wait_for_new_foreground_window(previous_hwnd)
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

    def create_file(self, path: str, content: str = "") -> OSActionResult:
        try:
            full_path = os.path.expandvars(os.path.expanduser(path))
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
                # string. With shell=True on Windows, subprocess rejoins the
                # argument list into one command line and hands it to
                # cmd.exe, so a path containing shell metacharacters (e.g.
                # `& calc.exe`) would execute as a second command. The list
                # form without shell=True passes argv directly to
                # CreateProcess with no shell involved.
                subprocess.Popen([candidate, os.path.expandvars(os.path.expanduser(path))])
            else:
                raise FileNotFoundError(f"Application not found: {app_name}")
            return OSActionResult(success=True, message=f"Opened {path} in {app_name}")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def get_active_window(self) -> OSActionResult:
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return OSActionResult(success=False, message="", error="No foreground window")

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            title_buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, length + 1)
            title = title_buf.value or "(untitled window)"

            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            process_name = "unknown process"
            # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) is enough to read the
            # image name without needing the broader (and often
            # permission-denied-on-elevated-processes) PROCESS_QUERY_INFORMATION.
            h_process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
            if h_process:
                try:
                    buf = ctypes.create_unicode_buffer(260)
                    size = wintypes.DWORD(260)
                    if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                        process_name = os.path.basename(buf.value)
                finally:
                    ctypes.windll.kernel32.CloseHandle(h_process)

            return OSActionResult(success=True, message=f"{process_name} — \"{title}\"")
        except Exception as e:
            return OSActionResult(success=False, message="", error=str(e))

    def read_file(self, path: str, max_chars: int = 20000) -> OSActionResult:
        try:
            full_path = os.path.expandvars(os.path.expanduser(path))
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
