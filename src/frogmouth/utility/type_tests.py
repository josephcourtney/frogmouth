"""Support code for testing files for their potential type."""

from functools import singledispatch
from pathlib import Path

from httpx import URL

from frogmouth.data.config import load_config


@singledispatch
def maybe_markdown(resource: object) -> bool:
    """Determine whether the given resource looks like a Markdown file.

    Args:
        resource: The resource to test.

    Returns
    -------
        `True` if the resources looks like a Markdown file, `False` if not.
    """
    del resource
    return False


@maybe_markdown.register
def _(resource: Path) -> bool:
    return resource.suffix.lower() in load_config().markdown_extensions


@maybe_markdown.register
def _(resource: str) -> bool:
    return maybe_markdown(Path(resource))


@maybe_markdown.register
def _(resource: URL) -> bool:
    return maybe_markdown(resource.path)


def is_likely_url(candidate: str) -> bool:
    """Determine whether the given value looks like a URL.

    Args:
        candidate: The candidate to check.

    Returns
    -------
        `True` if the string is likely a URL, `False` if not.
    """
    # Quick and dirty for now.
    url = URL(candidate)
    return url.is_absolute_url and url.scheme in {"http", "https"}
