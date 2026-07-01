"""Build the cross-platform 'reveal in file manager' command (Qt-free, unit-testable)."""

from __future__ import annotations

import os
import sys


def reveal_command(path, platform: str | None = None) -> list[str]:
    """argv to open the OS file manager with `path` selected.

    On Windows, `/select,` must be glued to the (backslash-normalized) path as a
    single arg; Explorer is picky about both. On macOS, `open -R` selects the
    file in Finder. Other platforms are not supported.
    """
    platform = platform if platform is not None else sys.platform
    if platform == "win32":
        return ["explorer", f"/select,{os.path.normpath(str(path))}"]
    if platform == "darwin":
        return ["open", "-R", str(path)]
    raise NotImplementedError(f"reveal_command is not supported on platform {platform!r}")


def reveal_label(platform: str | None = None) -> str:
    """Button label for the reveal action, matching the current platform's file manager."""
    platform = platform if platform is not None else sys.platform
    if platform == "darwin":
        return "Reveal in Finder"
    return "Reveal in Explorer"
