"""Resolve image references for Markdown documents."""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from httpx import URL, AsyncClient, HTTPStatusError, RequestError

from frogmouth.utility.advertising import USER_AGENT

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ImageLoadResult:
    """The outcome of resolving an image reference."""

    location: str
    """A human readable representation of the resolved location."""

    payload: bytes | Path | None
    """Raw bytes or a filesystem path that the renderer can consume."""

    error: str | None = None
    """An optional error message when the lookup failed."""

    def as_stream(self) -> io.BytesIO | Path | None:
        """Return the payload in a form that the image widget understands."""
        if isinstance(self.payload, Path):
            return self.payload
        if isinstance(self.payload, bytes):
            return io.BytesIO(self.payload)
        return None


class ImageResolver:
    """Resolve Markdown image sources relative to a document location."""

    def __init__(
        self,
        client_factory: Callable[[], AsyncClient] | None = None,
    ) -> None:
        self._base_path: Path | None = None
        self._base_url: URL | None = None
        self._client_factory = client_factory or self._default_client_factory
        self._client: AsyncClient | None = None
        self._cache: dict[str, bytes] = {}
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close any underlying HTTP client resources."""
        async with self._lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    def update_location(self, location: Path | URL | None) -> None:
        """Record the location of the currently viewed document."""
        if isinstance(location, Path):
            if location.is_file() or location.suffix:
                self._base_path = location.parent
            else:
                self._base_path = location
            self._base_url = None
            logger.debug("Set image resolver base path to %s", self._base_path)
        elif isinstance(location, URL):
            self._base_url = location
            self._base_path = None
            logger.debug("Set image resolver base URL to %s", self._base_url)
        else:
            self._base_path = None
            self._base_url = None
            logger.debug("Cleared image resolver base location")

    async def resolve(self, source: str) -> ImageLoadResult:
        """Resolve an image path to local data."""
        if not source:
            return ImageLoadResult(location="", payload=None, error="Empty image source")

        url = self._coerce_url(source)
        if url is not None:
            return await self._resolve_remote(url)
        return await self._resolve_local(source)

    async def _resolve_local(self, source: str) -> ImageLoadResult:
        candidate = Path(source)
        if not candidate.is_absolute():
            base_path = self._base_path or Path.cwd()
            candidate = (base_path / candidate).expanduser().resolve()
        logger.debug("Resolving local image %s", candidate)
        if candidate.exists():
            return ImageLoadResult(location=str(candidate), payload=candidate)
        return ImageLoadResult(
            location=str(candidate),
            payload=None,
            error="Image file not found",
        )

    async def _resolve_remote(self, url: URL) -> ImageLoadResult:
        key = str(url)
        if key in self._cache:
            logger.debug("Using cached remote image %s", key)
            return ImageLoadResult(location=key, payload=self._cache[key])

        client = await self._ensure_client()
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
        except HTTPStatusError as error:
            logger.warning("Remote image %s returned error", url, exc_info=error)
            return ImageLoadResult(location=key, payload=None, error=str(error))
        except RequestError as error:
            logger.warning("Failed to fetch remote image %s", url, exc_info=error)
            return ImageLoadResult(location=key, payload=None, error=str(error))

        content = bytes(response.content)
        self._cache[key] = content
        logger.debug("Fetched remote image %s (%d bytes)", key, len(content))
        return ImageLoadResult(location=key, payload=content)

    def _coerce_url(self, source: str) -> URL | None:
        try:
            direct = URL(source)
        except ValueError:
            direct = None
        else:
            if direct.scheme in {"http", "https"}:
                return direct
            if direct.scheme:
                return None

        if self._base_url is None:
            return None

        joined = self._base_url.join(source)
        if joined.scheme in {"http", "https"}:
            return joined
        return None

    async def _ensure_client(self) -> AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    @staticmethod
    def _default_client_factory() -> AsyncClient:
        return AsyncClient(headers={"user-agent": USER_AGENT})


__all__ = ["ImageLoadResult", "ImageResolver"]
