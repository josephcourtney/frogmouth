"""Markdown widget with inline image support."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from markdown_it import MarkdownIt
from rich.style import Style
from rich.text import Text
from textual.await_complete import AwaitComplete
from textual.widgets import _markdown as base_markdown  # noqa: PLC2701

from frogmouth.utility.image_loader import ImageSupport, load_image_support
from frogmouth.utility.image_resolver import ImageResolver

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import URL
    from markdown_it.token import Token
    from textual import events


class MarkdownImage(base_markdown.MarkdownBlock):
    """A block dedicated to rendering an inline image."""

    DEFAULT_CSS = """
    MarkdownImage {
        margin: 1 0;
    }

    MarkdownImage.-link {
        text-style: underline;
    }
    """

    def __init__(
        self,
        markdown: ImageMarkdown,
        source: str,
        alt_text: str,
        title: str,
        style: Style,
        resolver: ImageResolver,
        support: ImageSupport | None,
        link_href: str | None,
        token: Token | None = None,
    ) -> None:
        super().__init__(markdown)
        if token is not None:
            super().__init__(markdown, token)  # type: ignore[misc]
        else:
            super().__init__(markdown)
        self._source = source
        self._alt_text = alt_text
        self._title = title
        self._style = style
        self._resolver = resolver
        self._support = support
        self._link_href = link_href
        self._load_task: asyncio.Task[None] | None = None
        self._image_widget = None
        self._last_error: str | None = None
        self._show_status(self._initial_caption)

    @property
    def image_widget(self):
        """Return the mounted image widget, if any."""
        return self._image_widget

    @property
    def error(self) -> str | None:
        """Return the last error message, if any."""
        return self._last_error

    @property
    def support_available(self) -> bool:
        """Return ``True`` when the textual-image integration is active."""
        return self._support is not None

    def _show_status(self, message: str | None) -> None:
        text = Text()
        if message:
            text.append(message, self._style)
        self.set_content(text)

    @property
    def _initial_caption(self) -> str:
        return self._alt_text or self._title or self._source

    async def on_mount(self) -> None:
        if self._support is None:
            self._last_error = "Inline images require textual-image"
            self._show_status(f"{self._initial_caption} ({self._last_error})")
            return
        self._load_task = asyncio.create_task(self._load())

    async def on_unmount(self) -> None:
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None

    async def on_click(self, event: events.Click) -> None:
        if self._link_href:
            event.stop()
            await self.action_link(self._link_href)

    async def _load(self) -> None:
        try:
            result = await self._resolver.resolve(self._source)
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            return
        except Exception as error:  # noqa: BLE001  # pragma: no cover - defensive fallback
            self._last_error = str(error)
            self._show_status(f"{self._initial_caption} ({self._last_error})")
            return
        finally:
            self._load_task = None

        if result.error:
            self._last_error = result.error
            caption = f"{self._initial_caption} ({result.error})" if self._initial_caption else result.error
            self._show_status(caption)
            return

        payload = result.as_stream()
        if payload is None:
            self._last_error = "Unsupported image payload"
            self._show_status(f"{self._initial_caption} ({self._last_error})")
            return

        widget_cls = self._support.widget
        image_widget = widget_cls(payload)
        self._image_widget = image_widget
        if self._link_href:
            self.add_class("-link")
            image_widget.can_focus = True
        self._last_error = None
        # Ensure the block’s intrinsic height isn’t pinned to a single text line.
        # We’ll rely on the mounted image widget to size the block.
        self.set_content(Text())
        caption = self._alt_text or self._title or result.location
        if result.location:
            self.tooltip = result.location
        await self.mount(image_widget)
        # Force a layout pass after mounting the image so we don't render only a 1-row strip.
        self.refresh(layout=True)


class ImageMarkdownParagraph(base_markdown.MarkdownParagraph):
    """A paragraph block that is aware of image tokens."""

    def build_from_token(self, token: Token) -> None:  # noqa: C901, PLR0912
        self._token = token
        style_stack: list[Style] = [Style()]
        link_stack: list[str | None] = [None]
        content = Text()
        has_non_image_text = False
        markdown: ImageMarkdown = self._markdown  # type: ignore[assignment]

        def attr_as_str(value: object) -> str:
            if isinstance(value, str):
                return value
            if value is None:
                return ""
            return str(value)

        for child in token.children or ():
            child_type = child.type
            if child_type == "text":
                content.append(child.content, style_stack[-1])
                has_non_image_text = True
            elif child_type == "hardbreak":
                content.append("\n")
                has_non_image_text = True
            elif child_type == "softbreak":
                content.append(" ", style_stack[-1])
                has_non_image_text = True
            elif child_type == "code_inline":
                content.append(
                    child.content,
                    style_stack[-1] + markdown.get_component_rich_style("code_inline", partial=True),
                )
                has_non_image_text = True
            elif child_type == "em_open":
                style_stack.append(
                    style_stack[-1] + markdown.get_component_rich_style("em", partial=True),
                )
            elif child_type == "strong_open":
                style_stack.append(
                    style_stack[-1] + markdown.get_component_rich_style("strong", partial=True),
                )
            elif child_type == "s_open":
                style_stack.append(
                    style_stack[-1] + markdown.get_component_rich_style("s", partial=True),
                )
            elif child_type == "link_open":
                href = child.attrs.get("href", "")
                action = f"link({href!r})"
                style_stack.append(style_stack[-1] + Style.from_meta({"@click": action}))
                link_stack.append(href)
            elif child_type == "image":
                block = MarkdownImage(
                    markdown=markdown,
                    source=attr_as_str(child.attrs.get("src", "")),
                    alt_text=attr_as_str(child.attrs.get("alt", "")),
                    title=attr_as_str(child.attrs.get("title", "")),
                    style=style_stack[-1],
                    resolver=markdown.image_resolver,
                    support=markdown.image_support,
                    link_href=link_stack[-1],
                    token=child,
                )
                self._blocks.append(block)
                if has_non_image_text:
                    caption = child.attrs.get("alt") or child.attrs.get("src") or "image"
                    content.append(f" [{caption}]", style_stack[-1])
            elif child_type == "link_close":
                style_stack.pop()
                link_stack.pop()
            elif child_type.endswith("_close"):
                style_stack.pop()
            elif child.content:
                content.append(child.content, style_stack[-1])
                has_non_image_text = True

        if not has_non_image_text and self._blocks:
            content = Text()
        self.set_content(content)


class ImageMarkdown(base_markdown.Markdown):
    """Drop-in replacement for Textual's Markdown widget with image support."""

    def __init__(
        self,
        markdown: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002 - match Textual signature
        classes: str | None = None,
        parser_factory: Callable[[], MarkdownIt] | None = None,
        resolver: ImageResolver | None = None,
        support: ImageSupport | None = None,
    ) -> None:
        super().__init__(
            markdown,
            name=name,
            id=id,
            classes=classes,
            parser_factory=parser_factory,
        )
        self._image_resolver = resolver or ImageResolver()
        self._image_support = support if support is not None else load_image_support()

    def _make_heading_block(self, token, block_id: str) -> base_markdown.MarkdownBlock:
        """Create a heading block compatible with multiple Textual versions.

        Textual ≤0.41 exposed `HEADINGS[tag]`.
        Textual ≥0.5x moved/renamed internals; provide fallbacks.
        """
        tag = token.tag
        level = int(tag[1:])  # 'h1' → 1
        # Legacy mapping if present.
        headings = getattr(base_markdown, "HEADINGS", None)
        if headings is not None:
            return headings[tag](self, id=block_id)
        # Newer API: try a generic heading class with level parameter.
        Heading = getattr(base_markdown, "MarkdownHeading", None)
        if Heading is not None:
            # Newer signatures take (self, token, id=...), older may accept (self, level=..., id=...)
            try:
                return Heading(self, token, id=block_id)
            except TypeError:
                return Heading(self, level=level, id=block_id)
        # Fallbacks by class name pattern.
        for name in (f"MarkdownH{level}", f"MarkdownHeading{level}"):
            cls = getattr(base_markdown, name, None)
            if cls is not None:
                try:
                    return cls(self, token, id=block_id)
                except TypeError:
                    return cls(self, id=block_id)
        msg = "Unable to locate Markdown heading block in Textual"
        raise AttributeError(msg)

    @property
    def image_support(self) -> ImageSupport | None:
        return self._image_support

    @property
    def image_resolver(self) -> ImageResolver:
        return self._image_resolver

    def set_resource_location(self, location: Path | URL | None) -> None:
        self._image_resolver.update_location(location)

    async def load(self, path: Path) -> None:
        self.set_resource_location(path)
        await super().load(path)

    def update(self, markdown: str) -> AwaitComplete:  # noqa: C901, PLR0912, PLR0915
        output: list[base_markdown.MarkdownBlock] = []
        stack: list[base_markdown.MarkdownBlock] = []
        parser = MarkdownIt("gfm-like") if self._parser_factory is None else self._parser_factory()

        block_id: int = 0
        self._table_of_contents = []

        for token in parser.parse(markdown):
            if token.type == "heading_open":
                block_id += 1
                stack.append(self._make_heading_block(token, f"block{block_id}"))
            elif token.type == "hr":
                output.append(base_markdown.MarkdownHorizontalRule(self))
            elif token.type == "paragraph_open":
                stack.append(ImageMarkdownParagraph(self, token))
            elif token.type == "paragraph_close":
                output.extend(stack.pop().children)
            elif token.type == "blockquote_open":
                stack.append(base_markdown.MarkdownBlockQuote(self))
            elif token.type == "bullet_list_open":
                stack.append(base_markdown.MarkdownBulletList(self))
            elif token.type == "ordered_list_open":
                stack.append(base_markdown.MarkdownOrderedList(self))
            elif token.type == "list_item_open":
                if token.info:
                    stack.append(base_markdown.MarkdownOrderedListItem(self, token.info))
                else:
                    item_count = sum(
                        1 for block in stack if isinstance(block, base_markdown.MarkdownUnorderedListItem)
                    )
                    stack.append(
                        base_markdown.MarkdownUnorderedListItem(
                            self,
                            self.BULLETS[item_count % len(self.BULLETS)],
                        )
                    )
            elif token.type == "table_open":
                stack.append(base_markdown.MarkdownTable(self))
            elif token.type == "tbody_open":
                stack.append(base_markdown.MarkdownTBody(self))
            elif token.type == "thead_open":
                stack.append(base_markdown.MarkdownTHead(self))
            elif token.type == "tr_open":
                stack.append(base_markdown.MarkdownTR(self))
            elif token.type == "th_open":
                stack.append(base_markdown.MarkdownTH(self))
            elif token.type == "td_open":
                stack.append(base_markdown.MarkdownTD(self))
            elif token.type.endswith("_close"):
                block = stack.pop()
                if token.type == "heading_close":
                    # Robustly derive the heading text across Textual versions.
                    # Prefer the text captured from the preceding inline token, if present.
                    heading = getattr(block, "_frog_heading_text", None)
                    if heading is None:
                        # Fallback to legacy private attribute if available.
                        heading = getattr(getattr(block, "_text", None), "plain", "")
                    level = int(token.tag[1:])
                    self._table_of_contents.append((level, heading, block.id))
                if stack:
                    stack[-1]._blocks.append(block)  # noqa: SLF001
                else:
                    output.append(block)
            elif token.type == "inline":
                # If we're inside a heading, record its visible text for the ToC.
                if stack and stack[-1].__class__.__name__.startswith(("MarkdownH", "MarkdownHeading")):
                    stack[-1]._frog_heading_text = token.content
                else:
                    stack[-1].build_from_token(token)
            elif token.type in {"fence", "code_block"}:
                (stack[-1]._blocks if stack else output).append(  # noqa: SLF001
                    base_markdown.MarkdownFence(self, token.content.rstrip(), token.info)
                )
            else:
                external = self.unhandled_token(token)
                if external is not None:
                    (stack[-1]._blocks if stack else output).append(external)  # noqa: SLF001

        self.post_message(
            base_markdown.Markdown.TableOfContentsUpdated(self, self._table_of_contents).set_sender(self)
        )
        markdown_block = self.query("MarkdownBlock")

        async def await_update() -> None:
            """Update in a single batch."""
            with self.app.batch_update():
                await markdown_block.remove()
                await self.mount_all(output)

        return AwaitComplete(await_update())


__all__ = ["ImageMarkdown", "ImageMarkdownParagraph", "MarkdownImage"]
