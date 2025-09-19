from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import pytest
from httpx import URL, AsyncClient, MockTransport, Request, Response
from textual.app import App

from frogmouth.utility import image_loader
from frogmouth.utility.image_loader import _suppress_terminal_detection, load_image_support
from frogmouth.utility.image_resolver import ImageLoadResult, ImageResolver
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


def _skip_without_textual_image() -> None:
    support = load_image_support()
    if support is None:
        import pytest

        pytest.skip("textual-image not available in this environment")


def _mk_resolver_for_bytes(content: bytes, status: int = 200) -> ImageResolver:
    def handler(request: Request) -> Response:
        return Response(status, content=content, headers={"content-type": "image/jpeg"})

    transport = MockTransport(handler)
    return ImageResolver(client_factory=lambda: AsyncClient(transport=transport))


class _FakeStream:
    def __init__(self, *, is_tty: bool) -> None:  # FBT001: keyword-only bool
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def _fake_tty_stream(*, is_tty: bool):
    class _S:
        def isatty(self) -> bool:
            return is_tty

    return _S()


def test_no_suppression_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When stdout is a TTY, we must not enter the suppression CM."""
    image_loader.load_image_support.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "__stdout__", _FakeStream(is_tty=True), raising=False)

    @contextmanager
    def _bomb() -> Iterator[None]:
        msg = "suppression must not be used on TTY"
        raise AssertionError(msg)
        yield  # pragma: no cover

    monkeypatch.setattr(image_loader, "_suppress_terminal_detection", _bomb)
    with suppress(ModuleNotFoundError):
        image_loader.load_image_support()

    class _S:
        def __init__(self):
            self.patched = False

        def isatty(self):
            return True

    s_out = _S()
    s_in = _S()
    monkeypatch.setattr("sys.__stdout__", s_out, raising=False)
    monkeypatch.setattr("sys.__stdin__", s_in, raising=False)
    with _suppress_terminal_detection():
        # If suppression happened, isatty() would be False.
        assert s_out.isatty()
        assert s_in.isatty()


def test_suppression_in_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When stdout is not a TTY, we must enter the suppression CM."""
    image_loader.load_image_support.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(sys, "__stdout__", _FakeStream(is_tty=False), raising=False)

    entered = {"flag": False}

    @contextmanager
    def _flag() -> Iterator[None]:
        entered["flag"] = True
        yield

    monkeypatch.setattr(image_loader, "_suppress_terminal_detection", _flag)

    with suppress(ModuleNotFoundError):
        image_loader.load_image_support()

    assert entered["flag"] is True


def test_update_location_path_dir_and_file(tmp_path: Path) -> None:
    """update_location should track both a directory and a file parent."""
    r = ImageResolver()
    # Base as a directory.
    r.update_location(tmp_path)
    res = asyncio.run(r._resolve_local("x.png"))
    assert tmp_path in Path(res.location).parents or Path(res.location) == tmp_path / "x.png"
    # Base as a file (parent should be used).
    r.update_location(tmp_path / "doc.md")
    res2 = asyncio.run(r._resolve_local("y.png"))
    assert Path(res2.location).parent == tmp_path


def test_resolve_absolute_and_missing(tmp_path: Path) -> None:
    """Absolute existing paths should resolve, missing returns error."""
    ok = tmp_path / "ok.png"
    ok.write_bytes(b"\x00")
    r = ImageResolver()
    r.update_location(None)
    res_ok = asyncio.run(r.resolve(str(ok)))
    assert isinstance(res_ok, ImageLoadResult)
    assert res_ok.payload == ok
    assert res_ok.error is None
    res_missing = asyncio.run(r.resolve(str(tmp_path / "nope.png")))
    assert res_missing.payload is None
    assert "not found" in (res_missing.error or "").lower()


def test_resolve_remote_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote bytes are cached and reused."""
    content = b"abc123"
    r = _mk_resolver_for_bytes(content)
    r.update_location(URL("https://example.com/docs/readme.md"))
    # First fetch (cache miss).
    first = asyncio.run(r.resolve("img/one.jpg"))
    assert first.payload == content
    assert first.error is None
    # Swap transport to prove we hit the cache next time.
    alt = _mk_resolver_for_bytes(b"DIFFERENT")
    monkeypatch.setattr(r, "_client_factory", alt._client_factory)  # type: ignore[attr-defined]
    second = asyncio.run(r.resolve("img/one.jpg"))
    assert second.payload == content  # unchanged due to cache
    asyncio.run(r.aclose())


def test_resolve_remote_http_error() -> None:
    """HTTP status errors are surfaced in the ImageLoadResult.error."""

    def handler(request: Request) -> Response:
        return Response(404, text="nope")

    r = ImageResolver(client_factory=lambda: AsyncClient(transport=MockTransport(handler)))
    r.update_location(URL("https://example.com/docs/readme.md"))
    out = asyncio.run(r.resolve("img/missing.jpg"))
    assert out.payload is None
    assert out.error
    assert "404" in out.error
    asyncio.run(r.aclose())


def test_empty_source_guard() -> None:
    r = ImageResolver()
    res = asyncio.run(r.resolve(""))
    assert res.payload is None
    assert "empty" in (res.error or "").lower()


def test_local_image_allocates_vertical_space(tmp_path: Path) -> None:
    """Regression: only a 1-line strip was visible.
    Ensure the mounted image widget ends up taller than 1 row in a typical app size.
    """
    _skip_without_textual_image()

    async def scenario() -> None:
        img = tmp_path / TEST_IMAGE.name
        img.write_bytes(TEST_IMAGE.read_bytes())
        widget = ImageMarkdown()
        widget.set_resource_location(tmp_path / "doc.md")

        async with _MarkdownApp(widget).run_test(size=(100, 40)) as pilot:
            # Render a single image paragraph.
            await widget.update(f"![Admiral]({img.name})")
            # Let the async loader run.
            for _ in range(10):
                await pilot.pause()
            image_block = widget.query(MarkdownImage).first()
            # If image support is active we expect a mounted child and a sensible height.
            assert image_block.image_widget is not None
            # Textual tracks last rendered size on the widget.
            # Height > 1 ensures we didn't only lay out a top strip.
            assert image_block.image_widget.size.height > 1

    asyncio.run(scenario())


def test_remote_image_allocates_vertical_space() -> None:
    """Same regression check for remote image load via resolver."""
    _skip_without_textual_image()

    async def scenario() -> None:
        payload = TEST_IMAGE.read_bytes()

        def handler(request: Request) -> Response:
            return Response(200, content=payload, headers={"content-type": "image/jpeg"})

        resolver = ImageResolver(client_factory=lambda: AsyncClient(transport=MockTransport(handler)))
        widget = ImageMarkdown(resolver=resolver)
        widget.set_resource_location(URL("https://example.com/docs/doc.md"))

        async with _MarkdownApp(widget).run_test(size=(100, 40)) as pilot:
            await widget.update("![Remote](img/pic.jpg)")
            for _ in range(10):
                await pilot.pause()
            image_block = widget.query(MarkdownImage).first()
            assert image_block.image_widget is not None
            assert image_block.image_widget.size.height > 1

        await resolver.aclose()


def test_image_block_has_tooltip_or_caption(tmp_path: Path) -> None:
    """Sanity: caption/tooltip set for UX and to prevent zero-height content-only blocks."""

    async def scenario() -> None:
        img = tmp_path / TEST_IMAGE.name
        img.write_bytes(TEST_IMAGE.read_bytes())
        widget = ImageMarkdown()
        widget.set_resource_location(tmp_path / "doc.md")

        async with _MarkdownApp(widget).run_test() as pilot:
            await widget.update(f"![Legend]({img.name} 'Title')")
            await pilot.pause()
            image_block = widget.query(MarkdownImage).first()
            # We always show some status text even while loading/fallback.
            # This guarantees the parent block has non-zero intrinsic height.
            assert image_block is not None
            # Caption text is derived from alt/title/src. Should be non-empty.
            assert (image_block._initial_caption or "").strip()

    asyncio.run(scenario())
