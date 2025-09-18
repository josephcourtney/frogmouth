"""Tests for the Markdown viewer widget."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

from httpx import URL

from frogmouth.widgets.viewer import Viewer

if TYPE_CHECKING:
    from pathlib import Path


def test_visit_local_uses_keyword_arguments(tmp_path: Path) -> None:
    """Ensure local visits pass the remember flag as a keyword argument."""
    viewer = Viewer()
    mock_local_load = Mock()
    viewer._local_load = mock_local_load  # type: ignore[assignment]

    document = tmp_path / "doc.md"
    document.write_text("content")

    viewer.visit(document)

    mock_local_load.assert_called_once_with(document.resolve(), remember=True)


def test_visit_remote_uses_keyword_arguments() -> None:
    """Ensure remote visits pass the remember flag as a keyword argument."""
    viewer = Viewer()
    mock_remote_load = Mock()
    viewer._remote_load = mock_remote_load  # type: ignore[assignment]

    location = URL("https://example.com/doc.md")

    viewer.visit(location)

    mock_remote_load.assert_called_once_with(location, remember=True)
