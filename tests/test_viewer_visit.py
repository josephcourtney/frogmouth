"""Tests for the Markdown viewer widget."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from httpx import URL, Response
from textual.app import App

from frogmouth.widgets.viewer import Viewer

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


async def _noop() -> None:
    # RUF029: keep as async but actually await something
    await asyncio.sleep(0)


class _ViewerApp(App[None]):
    """Minimal Textual app to host a Viewer for DOM-dependent ops."""

    def __init__(self, viewer: Viewer) -> None:
        super().__init__()
        self._viewer = viewer

    def compose(self):  # type: ignore[override]
        yield self._viewer


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


def test__local_load_calls_post_load_with_keyword(tmp_path: Path) -> None:
    """_local_load must pass 'remember' by keyword to _post_load."""

    async def scenario() -> None:
        # Create a trivial markdown file to "load"
        doc = tmp_path / "doc.md"
        doc.write_text("# title\n")

        viewer = Viewer()
        app = _ViewerApp(viewer)

        async with app.run_test():
            # Stub out the document.load coroutine
            viewer.document.load = AsyncMock(return_value=None)  # type: ignore[attr-defined]

            # Spy on _post_load to verify call signature
            post_load = Mock()
            viewer._post_load = post_load  # type: ignore[assignment]

            # Call the undecorated coroutine to avoid Worker scheduling
            await Viewer._local_load.__wrapped__(viewer, doc, remember=True)  # type: ignore[attr-defined]

            # Assert keyword usage and values
            assert post_load.call_count == 1
            args, kwargs = post_load.call_args
            # Only 'location' may be positional
            assert len(args) == 1
            assert args[0] == doc
            assert kwargs == {"remember": True}

    asyncio.run(scenario())


def test__remote_load_calls_post_load_with_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """_remote_load must pass 'remember' by keyword to _post_load."""

    async def scenario() -> None:
        viewer = Viewer()
        app = _ViewerApp(viewer)

        async with app.run_test():
            # Prevent UI dialogs by ensuring "happy path"
            viewer.document.set_resource_location = Mock()  # type: ignore[attr-defined]
            viewer.document.update = Mock()  # type: ignore[attr-defined]
            post_load = Mock()
            viewer._post_load = post_load  # type: ignore[assignment]

            # Create a fake AsyncClient that returns a markdown-ish response
            class _FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
                    return None

                async def get(self, *args: object, **_kwargs: object) -> Response:
                    # httpx requires a Request on the Response for raise_for_status()
                    from httpx import Request

                    url_ = str(args[0]) if args else "https://example.invalid/"
                    req = Request("GET", url_)
                    return Response(
                        200, text="# hello\n", headers={"content-type": "text/markdown"}, request=req
                    )

            # Patch the AsyncClient used in the module under test
            monkeypatch.setattr("frogmouth.widgets.viewer.AsyncClient", _FakeClient)

            # Patch the AsyncClient used in the module under test
            monkeypatch.setattr("frogmouth.widgets.viewer.AsyncClient", _FakeClient)

            url = URL("https://example.com/readme.md")
            await Viewer._remote_load.__wrapped__(viewer, url, remember=False)  # type: ignore[attr-defined]

            # Verify keyword-only call
            assert post_load.call_count == 1
            args, kwargs = post_load.call_args
            assert len(args) == 1
            assert args[0] == url
            assert kwargs == {"remember": False}

    asyncio.run(scenario())
