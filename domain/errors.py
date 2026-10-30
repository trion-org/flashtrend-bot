"""Structured errors (docs/03 + 04): every failure carries code, message, details and trace_id."""
from __future__ import annotations

from dataclasses import dataclass, field

YT_QUOTA = "YT_QUOTA"
YT_AUTH = "YT_AUTH"
GEMINI_RATE_LIMIT = "GEMINI_RATE_LIMIT"
GEMINI_SCHEMA = "GEMINI_SCHEMA"
LLM_DISABLED = "LLM_DISABLED"
DB_WRITE = "DB_WRITE"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
TIMEOUT = "TIMEOUT"
UNEXPECTED = "UNEXPECTED"


@dataclass
class FlashTrendError(Exception):
    code: str
    message: str
    details: dict = field(default_factory=dict)
    trace_id: str = ""

    def __post_init__(self) -> None:
        Exception.__init__(self, f"{self.code}: {self.message}")

    def to_json(self) -> dict:
        """The shape stored in ``runs.error``."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "trace_id": self.trace_id,
        }
GEMINI_API = "GEMINI_API"  # any non-429 Gemini HTTP failure (bad key, 5xx, …)
