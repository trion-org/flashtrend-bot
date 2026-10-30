"""Weekly ``HEAD url`` over every ``media`` row (docs/07): 404 only sets ``alive = false``."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from application.observer import NullObserver, Observer
from domain.clock import now_vn
from domain.models import Media


class MediaStore(Protocol):
    def list_media(self) -> list[Media]: ...

    def set_media_alive(self, media_id: str, alive: bool, checked_at: datetime) -> None: ...


@dataclass
class MediaCheckResult:
    checked: int = 0
    dead: int = 0
    unknown: int = 0


class CheckMedia:
    def __init__(
        self,
        store: MediaStore,
        probe: Callable[[str], bool | None],
        observer: Observer | None = None,
        clock: Callable[[], datetime] = now_vn,
    ) -> None:
        self._store, self._probe = store, probe
        self._obs = observer or NullObserver()
        self._clock = clock

    def run(self) -> MediaCheckResult:
        result = MediaCheckResult()
        for media in self._store.list_media():  # includes owner = 'estfstudio' rows
            alive = self._probe(media.url)
            if alive is None:  # network trouble is not evidence the file is gone
                result.unknown += 1
                continue
            self._store.set_media_alive(media.id, alive, self._clock())
            result.checked += 1
            if not alive:
                result.dead += 1
                self._obs.warn(f"media {media.id} is gone (404): {media.url}")
        self._obs.info(
            f"media check: {result.checked} checked, {result.dead} dead, {result.unknown} unknown"
        )
        return result
