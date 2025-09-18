"""Provides code for saving and loading bookmarks."""

from __future__ import annotations

from json import JSONEncoder, dumps, loads
from pathlib import Path
from typing import NamedTuple

from httpx import URL

from frogmouth.utility import is_likely_url

from .data_directory import data_directory


class Bookmark(NamedTuple):
    """A bookmark."""

    title: str
    """The title of the bookmark."""
    location: Path | URL
    """The location of the bookmark."""


def bookmarks_file() -> Path:
    """Get the location of the bookmarks file.

    Returns
    -------
        The location of the bookmarks file.
    """
    return data_directory() / "bookmarks.json"


class BookmarkEncoder(JSONEncoder):
    """JSON encoder for the bookmark data."""

    def default(self, o: object) -> object:
        """Handle the Path and URL values.

        Args:
            o: The object to handle.

        Return:
            The encoded object.
        """
        if isinstance(o, (Path, URL)):
            return str(o)
        return super().default(o)


def save_bookmarks(bookmarks: list[Bookmark]) -> None:
    """Save the given bookmarks.

    Args:
        bookmarks: The bookmarks to save.
    """
    bookmarks_file().write_text(dumps(bookmarks, indent=4, cls=BookmarkEncoder))


def load_bookmarks() -> list[Bookmark]:
    """Load the bookmarks.

    Returns
    -------
        The bookmarks.
    """
    return (
        [
            Bookmark(title, URL(location) if is_likely_url(location) else Path(location))
            for (title, location) in loads(bookmarks.read_text())
        ]
        if (bookmarks := bookmarks_file()).exists()
        else []
    )
