from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from httpx import URL, AsyncClient, MockTransport, Request, Response
from textual.app import App

from frogmouth.utility.image_loader import load_image_support
from frogmouth.utility.image_resolver import ImageResolver
from frogmouth.widgets.markdown import ImageMarkdown, MarkdownImage

if TYPE_CHECKING:
    import pytest

TEST_IMAGE = Path("tests/data/gracehopper.jpg")


class _MarkdownApp(App[None]):
    def __init__(self, widget: ImageMarkdown) -> None:
        super().__init__()
        self._widget = widget

    def compose(self):  # type: ignore[override]
        yield self._widget


def test_local_image_mounts_widget(tmp_path: Path) -> None:
    async def scenario() -> None:
        image_path = tmp_path / TEST_IMAGE.name
        image_path.write_bytes(TEST_IMAGE.read_bytes())

        widget = ImageMarkdown()
        widget.set_resource_location(tmp_path / "document.md")

        async with _MarkdownApp(widget).run_test() as pilot:
            await widget.update(f"![Admiral]({TEST_IMAGE.name})")
            await pilot.pause()

            image_block = widget.query(MarkdownImage).first()
            assert image_block.support_available is (load_image_support() is not None)
            if image_block.support_available:
                for _ in range(5):
                    if image_block.error is None:
                        break
                    await pilot.pause()
                assert image_block.error is None
            else:
                assert image_block.image_widget is None
                assert image_block.error is not None

    asyncio.run(scenario())


def test_missing_local_image_reports_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        widget = ImageMarkdown()
        widget.set_resource_location(tmp_path / "document.md")

        async with _MarkdownApp(widget).run_test() as pilot:
            await widget.update(f"![Missing]({TEST_IMAGE.name})")
            await pilot.pause()

            image_block = widget.query(MarkdownImage).first()
            assert image_block.image_widget is None
            assert image_block.error is not None
            assert "not found" in image_block.error.lower()

    asyncio.run(scenario())


def test_remote_image_uses_resolver() -> None:
    async def scenario() -> None:
        image_bytes = TEST_IMAGE.read_bytes()

        def handler(request: Request) -> Response:
            return Response(200, content=image_bytes, headers={"content-type": "image/jpeg"})

        transport = MockTransport(handler)
        resolver = ImageResolver(client_factory=lambda: AsyncClient(transport=transport))

        widget = ImageMarkdown(resolver=resolver)
        widget.set_resource_location(URL("https://example.com/docs/readme.md"))

        async with _MarkdownApp(widget).run_test() as pilot:
            await widget.update("![Remote](images/gracehopper.jpg)")
            await pilot.pause()

            image_block = widget.query(MarkdownImage).first()
            if image_block.support_available:
                for _ in range(5):
                    if image_block.error is None:
                        break
                    await pilot.pause()
                assert image_block.error is None
                assert image_block.tooltip == "https://example.com/docs/images/gracehopper.jpg"
            else:
                assert image_block.image_widget is None
                assert image_block.error is not None

        await resolver.aclose()

    asyncio.run(scenario())


def test_graceful_degradation_when_textual_image_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        def no_support() -> None:
            return None

        no_support.cache_clear = lambda: None  # type: ignore[attr-defined]
        monkeypatch.setattr("frogmouth.widgets.markdown.load_image_support", no_support)
        load_image_support.cache_clear()

        widget = ImageMarkdown()

        async with _MarkdownApp(widget).run_test() as pilot:
            await widget.update("![Alt](missing.png)")
            await pilot.pause()

            image_block = widget.query(MarkdownImage).first()
            assert not image_block.support_available
            assert image_block.image_widget is None
            assert image_block.error is not None
            assert "textual-image" in image_block.error.lower()

    asyncio.run(scenario())
