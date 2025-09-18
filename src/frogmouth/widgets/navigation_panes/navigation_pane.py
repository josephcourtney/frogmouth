"""Provides a base class for all navigation panes."""

from textual.widgets import TabbedContent, TabPane
from typing_extensions import Self


class NavigationPane(TabPane):
    """Base class for panes within the navigation sidebar."""

    def set_focus_within(self) -> None:
        """Set the focus on the correct child within the navigation pane."""

    def activate(self) -> Self:
        """Activate the navigation pane.

        Returns
        -------
            Self.
        """
        if self.parent is None:
            msg = "Navigation pane must have a parent before activation."
            raise RuntimeError(msg)
        if self.id is not None and isinstance(self.parent.parent, TabbedContent):
            self.parent.parent.active = self.id
        return self
