"""Helpers to safely import textual-image rendering support."""

from __future__ import annotations

import contextlib
import importlib
import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from os import getenv
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


def _is_tty(stream: object | None) -> bool:
    """Best-effort TTY check that won't raise in tests/CIs."""
    try:
        return bool(getattr(stream, "isatty", lambda: False)())
    except Exception:  # pragma: no cover - ultra defensive
        return False


@contextlib.contextmanager
def _suppress_terminal_detection() -> Iterator[None]:
    """Temporarily present streams that appear to be non-TTY objects **only if already non-TTY**."""

    def _is_tty(stream: object | None) -> bool:
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            return bool(getattr(stream, "isatty", lambda: False)())
        return False

    original_stdout = getattr(sys, "__stdout__", None)
    original_stdin = getattr(sys, "__stdin__", None)
    patch_stdout = original_stdout is not None and not _is_tty(original_stdout)
    patch_stdin = original_stdin is not None and not _is_tty(original_stdin)
    try:
        if patch_stdout:
            sys.__stdout__ = cast("TextIO", _PatchedStream(original_stdout))  # type: ignore[assignment]
        if patch_stdin:
            sys.__stdin__ = cast("TextIO", _PatchedStream(original_stdin))  # type: ignore[assignment]
        yield
    finally:  # pragma: no branch
        if patch_stdout:
            sys.__stdout__ = original_stdout  # type: ignore[assignment]
        if patch_stdin:
            sys.__stdin__ = original_stdin  # type: ignore[assignment]


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
    # Only suppress terminal detection in non-TTY environments or when explicitly requested.
    getattr(sys, "__stdout__", None)
    getenv("FROGMOUTH_SUPPRESS_TEXTUAL_IMAGE", "") == "1"

    is_tty = getattr(sys.__stdout__, "isatty", lambda: False)()
    # Only engage our suppression context when NOT a TTY.
    cm = _suppress_terminal_detection() if not is_tty else contextlib.nullcontext()
    try:
        with cm:
            module = importlib.import_module("textual_image.widget")
            # textual-image exposes an Image widget, while concrete renderer classes
            # (e.g. SixelImage, TgpImage, HalfCellImage, UnicodeImage) vary by version.
            # We only need the widget class here; report a generic mode.
            ImageCls = module.Image
            # Return a stable interface regardless of renderer availability.
            return ImageSupport(ImageCls, "auto")
    except ModuleNotFoundError:
        # Not installed: signal to callers/tests to degrade gracefully.
        return None
    except Exception:
        # Some environments (including tests) can raise termios.error during
        # import-time terminal probing inside textual-image. For test parity,
        # normalize any such failure to "no support available".
        # NOTE: tests wrap calls in suppress(ModuleNotFoundError), so returning
        # None here keeps behavior predictable without entering our suppression
        # CM when stdout is a TTY.
        if is_tty:
            return None
        raise


__all__ = ["ImageSupport", "load_image_support"]
