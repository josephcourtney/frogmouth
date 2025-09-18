"""General utility and support code."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from .forge import (
    build_raw_bitbucket_url,
    build_raw_codeberg_url,
    build_raw_github_url,
    build_raw_gitlab_url,
)

__all__ = [
    "build_raw_bitbucket_url",
    "build_raw_codeberg_url",
    "build_raw_github_url",
    "build_raw_gitlab_url",
    "is_likely_url",
    "maybe_markdown",
]

if TYPE_CHECKING:
    from .type_tests import is_likely_url as _is_likely_url
    from .type_tests import maybe_markdown as _maybe_markdown

    is_likely_url = _is_likely_url
    maybe_markdown = _maybe_markdown


_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "is_likely_url": ("frogmouth.utility.type_tests", "is_likely_url"),
    "maybe_markdown": ("frogmouth.utility.type_tests", "maybe_markdown"),
}


def __getattr__(name: str) -> object:
    """Dynamically resolve lazily imported members."""
    try:
        module_name, attr_name = _LAZY_IMPORTS[name]
    except KeyError as exc:  # pragma: no cover - defensive programming
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg) from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:  # pragma: no cover - trivial proxy
    return sorted({*globals(), *__all__})
