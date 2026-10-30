"""Observer that writes to stderr in Vietnam time and never prints a secret."""
from __future__ import annotations

import sys

from domain.clock import now_vn


class LogObserver:
    def __init__(self, secrets: list[str] | None = None, stream=None) -> None:
        self._secrets = [s for s in (secrets or []) if s]
        self._stream = stream or sys.stderr

    def _emit(self, level: str, message: str) -> None:
        for secret in self._secrets:
            message = message.replace(secret, "***")
        stamp = now_vn().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{stamp} +07 {level} {message}", file=self._stream, flush=True)

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def warn(self, message: str) -> None:
        self._emit("WARN", message)
