"""Build the Windows 'reveal in Explorer' command (Qt-free, unit-testable)."""

from __future__ import annotations

import os


def reveal_command(path) -> list[str]:
    """argv to open Explorer with `path` selected. `/select,` must be glued to the
    (backslash-normalized) path as a single arg; Explorer is picky about both."""
    return ["explorer", f"/select,{os.path.normpath(str(path))}"]
