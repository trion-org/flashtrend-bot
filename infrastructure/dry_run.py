"""Read-only view of a store for ``--dry-run``: real reads, every write is dropped."""
from __future__ import annotations

from application.ports import DigestStore


class DryRunStore:
    _WRITES = frozenset({
        "open_run", "finish_run", "upsert_channels", "upsert_videos", "insert_snapshots",
        "insert_candidates", "upsert_embeddings", "insert_ideas", "update_idea_llm",
        "insert_media", "cleanup",
    })

    def __init__(self, inner: DigestStore) -> None:
        self._inner = inner

    def find_media(self, sha256):  # nothing is uploaded, so nothing is reused
        return None

    def __getattr__(self, name: str):
        if name in self._WRITES:
            return lambda *args, **kwargs: ({} if name == "cleanup" else None)
        return getattr(self._inner, name)
