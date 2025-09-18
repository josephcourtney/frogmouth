# Plan to integrate textual-image image rendering into Frogmouth Markdown viewer

1. **Add the new dependency**
   - Update `pyproject.toml` to declare `textual-image` as an application dependency (matching the version that works with the current Textual release).
   - Regenerate `uv.lock` so the resolver captures the new package and its transitive requirements.

2. **Create a safe import wrapper for textual-image**
   - Add a new utility module (e.g. `frogmouth/utility/image_loader.py`) that attempts to import `textual_image` widgets and renderables inside a guard that downgrades to “no image support” if the terminal detection raises `termios.error` / `textual_image._terminal.TerminalError`.
   - Ensure the wrapper temporarily patches `sys.__stdout__` / `sys.__stdin__` (or injects a fake `isatty()` returning `False`)while importing so tests running in non-TTY environments don’t crash.
   - Expose a small API from this module that returns either the usable `Image` widget class (and a flag describing the renderin
g mode) or `None` if images are unavailable, letting the rest of the app degrade gracefully with explanatory placeholders.

3. **Implement a reusable image resource resolver**
   - Introduce a helper class that, given the viewer’s current location, resolves Markdown image `src` attributes to actual data sources.
   - Support local files by resolving paths relative to the Markdown document directory and validating existence.
   - Support remote documents by combining relative URLs with the document URL, fetching the bytes with `httpx.AsyncClient`, and caching results to avoid repeated downloads.
   - Provide fallbacks (e.g. displaying alt text and error messages) when an image cannot be loaded.

4. **Extend the Markdown widget to build image blocks**
   - Subclass Textual’s `Markdown` (and any required block classes) inside a new module, overriding the inline token handling so that `image` tokens produce dedicated child widgets instead of the current `🖼` placeholder text.
   - Reuse most of the upstream implementation to preserve headings, TOC, lists, etc., but inject logic that:
     - Detects when a paragraph consists solely of an image vs. mixed content.
     - Creates a custom `MarkdownImage` block that mounts the `textual_image` widget retrieved from the import wrapper and loads the resolved image data asynchronously.
     - Falls back to the existing placeholder text when image support isn’t available.
   - Ensure the new block participates in theme updates and respects Markdown CSS (e.g. allowing width/height styling via fenced attribute syntax in the future).

5. **Integrate the new Markdown widget in the viewer**
   - Replace the `textual.widgets.Markdown` instance constructed in `frogmouth/widgets/viewer.py` with the custom image-aware Markdown class.
   - Pass the resolver helper (or at least the current document location) into the Markdown instance so image blocks know how to fetch their resources.
   - Update navigation/loading code to notify the Markdown widget whenever the base location changes (local path vs. URL) so images resolve correctly during history navigation and reloads.

6. **Add automated coverage for the new behaviour**
   - Write tests that render a simple Markdown snippet containing a local image and assert that the custom Markdown widget builds a `MarkdownImage` child (while the fallback placeholder appears if the asset is missing).
   - Add a test that simulates a remote document by monkeypatching the resolver to fetch bytes from an `httpx.MockTransport`, ensuring asynchronous downloads integrate without blocking the UI thread.
   - Include a regression test that verifies the viewer gracefully handles the absence of `textual_image` (forcing the import wrapper to return `None`).

7. **Document the new feature**
   - Update `README.md` (and, if necessary, in-app help text) to mention inline image support and outline any limitations (e.g. requires a terminal that supports colour image rendering).
   - Note any environment variables or fallbacks introduced by the wrapper so users running Frogmouth in non-TTY environments understand the behaviour.
