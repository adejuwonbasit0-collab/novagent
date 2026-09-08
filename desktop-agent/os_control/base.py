from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OSActionResult:
    success: bool
    message: str
    error: str | None = None


class OSController(ABC):
    """
    Every platform-specific controller implements this same surface, so the
    tool layer (and eventually the backend's tool handlers, called through
    this agent) never branches on platform — matches spec section 5's
    explicit instruction not to hard-code OS commands throughout the app.
    """

    @abstractmethod
    def open_application(self, app_name: str) -> OSActionResult: ...

    @abstractmethod
    def open_url(self, url: str) -> OSActionResult: ...

    @abstractmethod
    def open_folder(self, path: str) -> OSActionResult: ...

    @abstractmethod
    def lock_computer(self) -> OSActionResult: ...

    @abstractmethod
    def shutdown_computer(self) -> OSActionResult: ...

    @abstractmethod
    def restart_computer(self) -> OSActionResult: ...

    @abstractmethod
    def send_notification(self, title: str, message: str) -> OSActionResult: ...

    @abstractmethod
    def create_folder(self, path: str) -> OSActionResult: ...

    @abstractmethod
    def create_file(self, path: str, content: str = "") -> OSActionResult: ...

    @abstractmethod
    def type_text(self, text: str) -> OSActionResult: ...

    @abstractmethod
    def open_folder_in_application(self, path: str, app_name: str) -> OSActionResult: ...

    # MISSING FEATURE, now added: spec sections 13-14 are built entirely
    # around "what app am I using?" / "review the code I'm working on" —
    # and nothing in this codebase could answer either question. There was
    # no tool for it at all: not fake, not broken, just never built. These
    # two close that gap with the minimum needed to support both examples:
    # knowing what's currently focused, and reading a permitted file's
    # actual content back to the model.
    @abstractmethod
    def get_active_window(self) -> OSActionResult:
        ...

    @abstractmethod
    def read_file(self, path: str, max_chars: int = 20000) -> OSActionResult:
        ...

    @abstractmethod
    def take_screenshot(self) -> OSActionResult:
        ...

    @abstractmethod
    def show_desktop(self) -> OSActionResult:
        ...

    @abstractmethod
    def rename_file(self, old_path: str, new_path: str) -> OSActionResult:
        ...

    @abstractmethod
    def delete_file(self, path: str) -> OSActionResult:
        ...


def get_controller() -> OSController:
    import platform

    system = platform.system().lower()
    if system == "windows":
        from os_control.windows import WindowsController

        return WindowsController()
    if system == "darwin":
        from os_control.macos import MacOSController

        return MacOSController()
    from os_control.linux import LinuxController

    return LinuxController()
