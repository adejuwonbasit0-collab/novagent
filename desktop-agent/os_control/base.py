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
