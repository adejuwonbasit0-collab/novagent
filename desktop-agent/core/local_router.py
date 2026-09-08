from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalRoute:
    tool_name: str
    params: dict


_APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "notepad": "notepad.exe",
    "wordpad": "write.exe",
    "word pad": "write.exe",
    "paint": "mspaint.exe",
    "ms paint": "mspaint.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "control panel": "control.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "task manager": "taskmgr.exe",
}

_URL_RE = re.compile(r"^(?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?$", re.I)

_GOOGLE_SEARCH_PATTERNS = [
    re.compile(r"^(?:go\s+to\s+)?google\s+and\s+search(?:\s+for)?\s+(.+)$", re.I),
    re.compile(r"^search(?:\s+for)?\s+(.+?)\s+on\s+google$", re.I),
    re.compile(r"^google\s+(.+)$", re.I),
]

_OPEN_APP_RE = re.compile(r"^(?:open|launch|start|go to)\s+(?:the\s+)?(.+?)$", re.I)
_OPEN_IN_EDITOR_RE = re.compile(
    r"(?:open|launch)\s+(.+?)\s+in\s+(?:visual studio code|vs code|vscode)$", re.I
)
_CREATE_FOLDER_RE = re.compile(r"(?:create|make)\s+(?:a\s+)?folder(?:\s+named|\s+called)?\s+(.+)$", re.I)
_CREATE_FILE_RE = re.compile(r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?file(?:\s+named|\s+called)?\s+(.+)$", re.I)
_LOCK_RE = re.compile(r"^lock\s+(?:my\s+)?(?:computer|screen|pc|laptop)\.?$", re.I)
_SHUTDOWN_RE = re.compile(r"^(?:shut\s*down|power\s+off)\s+(?:my\s+)?(?:computer|pc|laptop)\.?$", re.I)
_RESTART_RE = re.compile(r"^(?:restart|reboot)\s+(?:my\s+)?(?:computer|pc|laptop)\.?$", re.I)
_SCREENSHOT_RE = re.compile(r"^(?:take\s+(?:a\s+)?screenshot|capture\s+(?:the\s+)?screen|screenshot)\.?$", re.I)
_SHOW_DESKTOP_RE = re.compile(r"^(?:show\s+(?:my\s+)?desktop|minimize\s+all(?:\s+windows)?)\.?$", re.I)
_ACTIVE_WINDOW_RE = re.compile(r"^(?:what\s+app\s+am\s+i\s+using|what\s+is\s+my\s+active\s+window|active\s+window)\??$", re.I)


def route_locally(message: str) -> LocalRoute | dict | None:
    text = message.strip()
    lowered = text.lower().rstrip(".").rstrip("?")

    if _LOCK_RE.match(lowered):
        return LocalRoute("lock_computer", {})

    if _SHUTDOWN_RE.match(lowered):
        return LocalRoute("shutdown_computer", {})

    if _RESTART_RE.match(lowered):
        return LocalRoute("restart_computer", {})

    if _SCREENSHOT_RE.match(lowered):
        return LocalRoute("take_screenshot", {})

    if _SHOW_DESKTOP_RE.match(lowered):
        return LocalRoute("show_desktop", {})

    if _ACTIVE_WINDOW_RE.match(lowered):
        return LocalRoute("get_active_window", {})

    for pattern in _GOOGLE_SEARCH_PATTERNS:
        search_match = pattern.match(lowered)
        if search_match:
            query = search_match.group(1).strip().strip('"')
            if query and query != "chrome":
                import urllib.parse
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
                return LocalRoute("open_url", {"url": url})

    editor_match = _OPEN_IN_EDITOR_RE.search(text)
    if editor_match:
        return LocalRoute(
            "open_folder_in_application",
            {"path": editor_match.group(1).strip().strip('"'), "app_name": "Visual Studio Code"},
        )

    folder_match = _CREATE_FOLDER_RE.search(text)
    if folder_match:
        name = folder_match.group(1).strip().strip('"')
        return LocalRoute("create_folder", {"path": str(Path.home() / "Desktop" / name)})

    file_match = _CREATE_FILE_RE.search(text)
    if file_match:
        name = file_match.group(1).strip().strip('"')
        if not re.search(r"\band\b|\bwith\b", name, re.I):
            return LocalRoute("create_file", {"path": str(Path.home() / "Desktop" / name), "content": ""})
        return None

    open_match = _OPEN_APP_RE.match(lowered)
    if open_match:
        requested = open_match.group(1).strip().strip('"')
        if requested in _APP_ALIASES:
            return LocalRoute("open_application", {"app_name": _APP_ALIASES[requested]})
        if requested == "google":
            return LocalRoute("open_url", {"url": "https://www.google.com"})
        if _URL_RE.match(requested):
            url = requested if requested.startswith(("http://", "https://")) else f"https://{requested}"
            return LocalRoute("open_url", {"url": url})
        return None

    return None
