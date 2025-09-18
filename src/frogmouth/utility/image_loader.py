"""Helpers to safely import textual-image rendering support."""

from __future__ import annotations

import contextlib
import importlib
import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator, TextIO, cast

logger = logging.getLogger(__name__)


class _PatchedStream:
    """Proxy that forces :func:`isatty` to return ``False``."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def __getattr__(self, name: str) -> object:  # pragma: no cover - passthrough
        return getattr(self._stream, name)

    @staticmethod
    def isatty() -> bool:
        return False


@contextlib.contextmanager
def _suppress_terminal_detection() -> Iterator[None]:
    """Temporarily present streams that appear to be non-TTY objects."""
    original_stdout = getattr(sys, "__stdout__", None)
    original_stdin = getattr(sys, "__stdin__", None)
    try:
        if original_stdout is not None:
            sys.__stdout__ = cast("TextIO", _PatchedStream(original_stdout))  # type: ignore[assignment]
        if original_stdin is not None:
            sys.__stdin__ = cast("TextIO", _PatchedStream(original_stdin))  # type: ignore[assignment]
        yield
    finally:  # pragma: no branch - restoration happens regardless of branch coverage
        if original_stdout is not None:
            sys.__stdout__ = original_stdout
        if original_stdin is not None:
            sys.__stdin__ = original_stdin


def _normalise_mode(renderable: object) -> str:
    """Create a human readable rendering mode description."""
    module = getattr(renderable, "__module__", "")
    if module.endswith("sixel"):
        return "sixel"
    if module.endswith("tgp"):
        return "tgp"
    if module.endswith("halfcell"):
        return "halfcell"
    if module.endswith("unicode"):
        return "unicode"
    return "auto"


@dataclass(frozen=True)
class ImageSupport:
    """Information describing the available image widget."""

    widget: type[object]
    mode: str


@lru_cache(maxsize=1)
def load_image_support() -> ImageSupport | None:
    """Attempt to import the ``textual_image`` widget safely.

    Returns
    -------
        An :class:`ImageSupport` instance if the dependency is installed and
        the current environment supports initialisation, otherwise ``None``.
    """
    try:
        with _suppress_terminal_detection():
            module = importlib.import_module("textual_image.widget")
    except ModuleNotFoundError:
        logger.info("textual-image is not installed; disabling inline images")
        return None
    except Exception as error:  # noqa: BLE001  # pragma: no cover - defensive fallback
        logger.warning("Unable to enable inline images", exc_info=error)
        return None

    image_cls: type[object] = module.Image
    renderable = getattr(image_cls, "_Renderable", None)
    mode = _normalise_mode(renderable) if renderable is not None else "auto"
    logger.debug("Inline images enabled via %s mode", mode)
    return ImageSupport(widget=image_cls, mode=mode)


__all__ = ["ImageSupport", "load_image_support"]
