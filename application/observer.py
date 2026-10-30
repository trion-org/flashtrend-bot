"""Progress/log port: no layer below presentation prints or logs directly."""
from __future__ import annotations

from typing import Protocol


class Observer(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...


class NullObserver:
    def info(self, message: str) -> None:
        pass

    def warn(self, message: str) -> None:
        pass
