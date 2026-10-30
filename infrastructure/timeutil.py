"""Timestamp helpers shared by the adapters. Everything leaves and enters as Vietnam time (+07:00)."""
from __future__ import annotations

import re
from datetime import datetime

from domain.clock import to_vn

_FRACTION = re.compile(r"\.(\d+)")


def parse_ts(value: str) -> datetime:
    """Parse ``2026-10-28T00:17:12.12345+00:00`` / ``…Z`` on Python 3.10 (strict ``fromisoformat``).

    Any offset is accepted (PostgREST and YouTube answer in UTC); the result is Vietnam time.
    """
    text = value.strip().replace("Z", "+00:00").replace(" ", "T", 1)
    text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    return to_vn(datetime.fromisoformat(text))


def iso(dt: datetime) -> str:
    """ISO-8601 with the ``+07:00`` offset, e.g. ``2026-10-28T07:17:12+07:00``."""
    return to_vn(dt).isoformat()
