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
   rename/move/copy file, and send_notification, but none of those have a
   matching backend Tool registered, so the LLM can never call them
   either — there's no schema to expose. Matching a phrase like "restart
   my computer" to a tool name that doesn't exist would be exactly the
   "button that pretends to work" spec section 47 forbids. Instead,
   UNSUPPORTED_PATTERNS below recognizes those requests and returns an
   honest "not available yet" answer with zero network calls, rather than
   either silently failing or letting the cloud LLM improvise a reply
   about an action nothing actually performed. (open_url used to be in
   this category too -- it now has a real backend Tool, see below.)
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

# A bare domain/URL typed or spoken after "open"/"go to" ("go to
# amazon.com", "open github.com/anthropics") -- this is what "I can tell it
# to go to this website giving it the url" needs. Deliberately requires a
# real TLD-shaped ending (.com/.org/.io/etc, or an explicit scheme) rather
# than matching any word with a dot in it, so "open version 2.0" or "open
# the q3.report file" don't get misread as URLs.
_URL_RE = re.compile(r"^(?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?$", re.I)

# "go to google and search for X" / "search for X on google" / "google X"
# (but not "google chrome", handled by _APP_ALIASES above, or a bare
# "google"/"go to google", handled as opening the homepage below) -- no
# separate search-API integration exists, so this builds a real Google
# search results URL directly. Deterministic, and it actually answers "go
# to Google and search for this name": the browser opens straight to the
# results instead of just the homepage.
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

    for pattern in _GOOGLE_SEARCH_PATTERNS:
        search_match = pattern.match(lowered)
        if search_match:
            query = search_match.group(1).strip().strip('"')
            if query and query != "chrome":  # "google chrome" -- not a search, handled by _APP_ALIASES
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
        # "create a file called notes.txt AND write today's date in it" --
        # that's dictating content, not just a bare filename. This fast
        # path only handles an empty file with a name; anything implying
        # content needs the cloud path so the LLM can compose real text
        # for create_file's `content` param, rather than local_router
        # trying to guess where the filename ends and instructions begin.
        if not re.search(r"\band\b|\bwith\b", name, re.I):
            return LocalRoute("create_file", {"path": str(Path.home() / "Desktop" / name), "content": ""})
        return None

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
        # "go to chrome" opens the Chrome app; "go to google" (bare, no
        # "search"/"and search for") means the Google homepage, not the
        # browser by name -- these are two different requests that happen
        # to share a company name, and conflating them was the actual bug
        # behind "chrome or google only should catch that I mean google
        # chrome": "google" alone was never mapped to anything before.
        if requested == "google":
            return LocalRoute("open_url", {"url": "https://www.google.com"})
        if _URL_RE.match(requested):
            url = requested if requested.startswith(("http://", "https://")) else f"https://{requested}"
            return LocalRoute("open_url", {"url": url})
        return None

    return None
