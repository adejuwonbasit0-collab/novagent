from __future__ import annotations

"""
Local-command fast path (spec section 10/39): recognizes requests that map
to a deterministic tool call and can skip the cloud LLM round-trip entirely.
This is intentionally narrow rather than clever — every entry here maps to
a tool that is ACTUALLY registered in backend/app/tools/*.py and reachable
end-to-end (backend -> WebSocket -> desktop-agent os_control). Two things
this module deliberately does NOT do:

1. It never invents a tool call for a capability that doesn't exist yet
   end-to-end. The desktop agent's WebSocket dispatch table
   (core/ws_client.py) has handlers for things like restart, sleep,
   rename/move/copy file, open_url, and send_notification, but none of
   those have a matching backend Tool registered, so the LLM can never
   call them either — there's no schema to expose. Matching a phrase like
   "restart my computer" to a tool name that doesn't exist would be
   exactly the "button that pretends to work" spec section 47 forbids.
   Instead, UNSUPPORTED_PATTERNS below recognizes those requests and
   returns an honest "not available yet" answer with zero network calls,
   rather than either silently failing or letting the cloud LLM improvise
   a reply about an action nothing actually performed.
2. It never guesses at reminders/schedule queries — natural-language time
   parsing ("remind me in 20 minutes", "every weekday at 6") is exactly
   the kind of task an LLM does far more reliably than a regex, and a
   wrong local guess here would silently create a reminder at the wrong
   time with no chance for the user to notice before it's already set.
   Those intentionally fall through to the cloud path.

Extending this list is the only thing you should need to do when a new
backend Tool is registered and its trigger phrasing is unambiguous enough
to route without an LLM.
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalRoute:
    tool_name: str
    params: dict


# App-name aliases that don't match their process/launch name 1:1. Anything
# not listed here is passed through to open_application as typed — the
# desktop agent's OSController implementations already handle common cases
# per-platform (see os_control/windows.py's own alias table for VS Code).
_APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
}

_OPEN_APP_RE = re.compile(r"^(?:open|launch|start|go to)\s+(?:the\s+)?(.+?)$", re.I)
_OPEN_IN_EDITOR_RE = re.compile(
    r"(?:open|launch)\s+(.+?)\s+in\s+(?:visual studio code|vs code|vscode)$", re.I
)
_CREATE_FOLDER_RE = re.compile(r"(?:create|make)\s+(?:a\s+)?folder(?:\s+named|\s+called)?\s+(.+)$", re.I)
_LOCK_RE = re.compile(r"^lock\s+(?:my\s+)?(?:computer|screen|pc|laptop)\.?$", re.I)
_SHUTDOWN_RE = re.compile(r"^(?:shut\s*down|power\s+off)\s+(?:my\s+)?(?:computer|pc|laptop)\.?$", re.I)

# Recognized but not yet wired end-to-end (see module docstring point 1).
# Each maps a set of required-word groups (all must appear somewhere in the
# message, in any order) to the honest, specific reason it can't run yet.
# Word-order-independent on purpose: "put my computer to sleep" and "sleep
# my computer" should both match "sleep" + "computer" — an earlier version
# of this used a single ordered regex per pattern and silently missed the
# first phrasing.
_UNSUPPORTED_WORD_GROUPS: list[tuple[list[re.Pattern], str]] = [
    ([re.compile(r"\brestart\b", re.I), re.compile(r"\b(computer|pc|laptop)\b", re.I)],
     "Restarting the computer isn't wired up yet — only lock and shut down are currently supported."),
    ([re.compile(r"\b(sleep|hibernate)\b", re.I), re.compile(r"\b(computer|pc|laptop)\b", re.I)],
     "Putting the computer to sleep isn't wired up yet — only lock and shut down are currently supported."),
    ([re.compile(r"\blog\s*out\b|\bsign\s*out\b", re.I)],
     "Logging out isn't wired up yet — only lock and shut down are currently supported."),
    ([re.compile(r"\b(rename|move|copy|delete)\b", re.I), re.compile(r"\bfile\b", re.I)],
     "File rename/move/copy/delete isn't wired up yet — I can create folders and open things for now."),
    ([re.compile(r"\bopen\b", re.I), re.compile(r"\b(url|website|link)\b|https?://", re.I)],
     "Opening a URL directly isn't wired up yet."),
    ([re.compile(r"\bsend\b", re.I), re.compile(r"\bnotification\b", re.I)],
     "Sending a standalone notification isn't wired up yet."),
]


def route_locally(message: str) -> LocalRoute | dict | None:
    """
    Returns:
    - LocalRoute(tool_name, params) if the message maps to a real,
      registered backend tool — caller should call that tool directly.
    - {"unsupported": <reason>} if the message clearly asks for a
      recognized-but-not-implemented capability — caller should show the
      reason directly, with no network call at all.
    - None if nothing matched — caller should fall through to the cloud
      chat path.
    """
    text = message.strip()
    lowered = text.lower().rstrip(".")

    for patterns, reason in _UNSUPPORTED_WORD_GROUPS:
        if all(p.search(lowered) for p in patterns):
            return {"unsupported": reason}

    if _LOCK_RE.match(lowered):
        return LocalRoute("lock_computer", {})

    if _SHUTDOWN_RE.match(lowered):
        return LocalRoute("shutdown_computer", {})

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

    open_match = _OPEN_APP_RE.match(lowered)
    if open_match:
        requested = open_match.group(1).strip().strip('"')
        # Only fast-path a small set of unambiguous app names. Anything
        # else ("open my project", "open the report") is ambiguous enough
        # (which report? which project folder?) that it should go through
        # the cloud path, which has more context and can ask a clarifying
        # question rather than guessing an executable name.
        if requested in _APP_ALIASES:
            return LocalRoute("open_application", {"app_name": _APP_ALIASES[requested]})
        return None

    return None
