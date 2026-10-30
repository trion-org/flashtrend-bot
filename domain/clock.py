"""The one timezone of the project: Vietnam (UTC+7, no daylight saving).

Every timestamp the bot creates, logs or serialises is Vietnam time. A fixed offset is exact for
Vietnam and needs no tz database (Windows/py3.10 safe). Instants from outside (YouTube, Postgres)
are converted at the edge with :func:`to_vn`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), "ICT")


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def to_vn(dt: datetime) -> datetime:
    """Same instant, expressed in Vietnam time (naive values are taken to already be VN)."""
    return dt.replace(tzinfo=VN_TZ) if dt.tzinfo is None else dt.astimezone(VN_TZ)
