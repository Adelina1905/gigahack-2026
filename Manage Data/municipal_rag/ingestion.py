"""Version-selection helpers for immutable municipal snapshots."""

from __future__ import annotations

from pathlib import Path


def newest_snapshots(root: Path) -> list[Path]:
    selected = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        files = sorted(directory.glob("*.json"), key=lambda item: (item.stat().st_mtime_ns, item.name))
        if files:
            selected.append(files[-1])
    return selected

