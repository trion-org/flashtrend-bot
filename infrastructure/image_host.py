"""Third-party image host (docs/07): POST a PNG, get a public URL. Supabase keeps only URL + sha256.

The endpoint is an internal API of a website, not a contracted image service: treat it as able to
vanish at any time. Callers must never let an upload failure fail a run. The response format was
never confirmed (docs/07 open question), so the URL is located structurally by :func:`find_url`.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import requests

from domain.models import MAX_IMAGE_BYTES

PREFERRED_KEYS = ("url", "link", "fileUrl", "file_url", "src", "path", "location")


class ImageHostError(RuntimeError):
    pass


def find_url(payload: object) -> str:
    """First public http(s) URL in a JSON response, preferring keys named like a URL."""
    found: list[tuple[int, str]] = []

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, str):
            if node.startswith(("http://", "https://")):
                rank = PREFERRED_KEYS.index(key) if key in PREFERRED_KEYS else len(PREFERRED_KEYS)
                found.append((rank, node))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)

    walk(payload)
    if not found:
        raise ImageHostError("the upload response contains no public URL")
    return min(found, key=lambda pair: pair[0])[1]


class HttpImageHost:
    def __init__(
        self,
        upload_url: str,
        session=None,
        timeout: float = 30.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = upload_url
        self._http = session or requests
        self._timeout = timeout
        self._retries = retries
        self._sleep = sleep

    def upload(self, png: bytes, filename: str) -> str:
        if len(png) > MAX_IMAGE_BYTES:
            raise ImageHostError("image is larger than 2 MB")
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = self._http.post(
                    self._url,
                    files={"file": (filename, png, "image/png")},
                    headers={"Accept": "application/json"},
                    timeout=self._timeout,
                )
                if resp.status_code >= 500:
                    raise ImageHostError(f"image host HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    raise ImageHostError(f"image host rejected the upload: HTTP {resp.status_code}")
                return find_url(resp.json())
            except (requests.RequestException, ValueError, ImageHostError) as exc:
                last = exc
                if isinstance(exc, ImageHostError) and "rejected" in str(exc):
                    break  # 4xx will not get better on retry
                if attempt < self._retries:
                    self._sleep(1.0 * (attempt + 1))
        raise ImageHostError(f"upload failed after {self._retries + 1} attempts: {last}")


def url_is_alive(url: str, session=None, timeout: float = 15.0) -> bool | None:
    """HEAD the URL: False on 404/410, True on 2xx/3xx, None when unknown (network error, 5xx)."""
    http = session or requests
    try:
        resp = http.head(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code in (404, 410):
        return False
    if resp.status_code < 400:
        return True
    return None
