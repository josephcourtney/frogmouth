"""Provides the local files navigation pane."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Iterable

from textual.message import Message
from textual.widgets import DirectoryTree

from frogmouth.utility import maybe_markdown

from .navigation_pane import NavigationPane

if TYPE_CHECKING:
    from httpx import URL
    from textual.app import ComposeResult


class FilteredDirectoryTree(DirectoryTree):  # pylint:disable=too-many-ancestors
    """A `DirectoryTree` filtered for the markdown viewer."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialise the filtered directory tree."""
        super().__init__(*args, **kwargs)
        self._last_filter_result: list[Path] = []

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter the directory tree for the Markdown viewer.

        Args:
            paths: The paths to be filtered.

        Returns
        -------
            The parts filtered for the Markdown viewer.

        The filtered set will include all filesystem entries that aren't
        hidden (in a Unix sense of hidden) which are either a directory or a
        file that looks like it could be a Markdown document.
        """
        try:
            filtered_paths = [
                path
                for path in paths
                if (not path.name.startswith(".") and path.is_dir())
                or (path.is_file() and maybe_markdown(path))
            ]
        except PermissionError:
            filtered_paths = []
        self._last_filter_result = filtered_paths
        return filtered_paths


class LocalFiles(NavigationPane):
    """Local file picking navigation pane."""

    DEFAULT_CSS: ClassVar[str] = """
    LocalFiles {
        height: 100%;
    }

    LocalFiles > DirectoryTree {
        background: $panel;
        width: 1fr;
    }

    LocalFiles > DirectoryTree:focus .tree--cursor, LocalFiles > DirectoryTree .tree--cursor {
        background: $accent 50%;
        color: $text;
    }
    """

    def __init__(self) -> None:
        """Initialise the local files navigation pane."""
        super().__init__("Local")
        self._tree: FilteredDirectoryTree | None = None

    @property
    def directory_tree(self) -> FilteredDirectoryTree:
        """Return the directory tree widget."""
        if self._tree is None:
            self._tree = self.query_one(FilteredDirectoryTree)
        return self._tree

    def compose(self) -> ComposeResult:
        """Compose the child widgets."""
        self._tree = FilteredDirectoryTree(Path("~").expanduser())
        yield self._tree

    def chdir(self, path: Path) -> None:
        """Change the filesystem view to the given directory.

        Args:
            path: The path to change to.
        """
        self.directory_tree.path = path

    def set_focus_within(self) -> None:
        """Focus the directory tree."""
        self.directory_tree.focus(scroll_visible=False)

    class Goto(Message):
        """Message that requests the viewer goes to a given location."""

        def __init__(self, location: Path | URL) -> None:
            """Initialise the history goto message.

            Args:
                location: The location to go to.
            """
            super().__init__()
            self.location = location
            """The location to go to."""

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle a file being selected in the directory tree.

        Args:
            event: The direct tree selection event.
        """
        event.stop()
        self.post_message(self.Goto(Path(event.path)))
