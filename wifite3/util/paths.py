#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Filesystem helpers for bundled Wifite3 data files.

The original Wifite3 code looks for ``ieee-oui.txt`` and wordlists relative to
the current working directory.  That breaks as soon as the tool is installed
with pip/pipx and run from somewhere else.  Everything in Wifite3 resolves
data through this module instead.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Return the bundled data directory, even inside a wheel/zip install."""
    try:
        from importlib.resources import files

        return Path(str(files("wifite3.data")))
    except Exception:
        return Path(__file__).resolve().parent.parent / "data"


def data_file(name: str) -> Path:
    """Return a path to a bundled data file (whether or not it exists)."""
    return data_dir() / name


def find_data_file(name: str, extra_dirs: list[str] | None = None) -> Path | None:
    """Find *name* in the working tree, user config dirs or bundled data."""
    candidates: list[Path] = []
    if extra_dirs:
        candidates.extend(Path(p) / name for p in extra_dirs)
    candidates.extend(
        [
            Path.cwd() / name,
            Path.home() / ".wifite3" / name,
            data_file(name),
            Path("/usr/share/ieee-data/oui.txt") if name == "ieee-oui.txt" else Path(),
        ]
    )
    for candidate in candidates:
        try:
            if candidate and candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def wordlist_paths() -> list[Path]:
    """Return usable wordlists, bundled first, then common system locations."""
    paths: list[Path] = []

    bundled = data_dir() / "wordlists"
    try:
        paths.extend(sorted(bundled.glob("*.txt")))
    except OSError:
        pass

    for candidate in (
        Path.cwd() / "wordlists",
        Path("/usr/share/dict/wordlists"),
        Path("/usr/local/share/dict/wordlists"),
        Path("/usr/share/wordlists"),
    ):
        try:
            if candidate.is_dir():
                paths.extend(sorted(candidate.glob("*.txt")))
        except OSError:
            continue

    for candidate in (
        Path("/usr/share/fuzzdb/wordlists-user-passwd/passwds/phpbb.txt"),
        Path("/usr/share/wordlists/fern-wifi/common.txt"),
    ):
        if candidate.is_file():
            paths.append(candidate)

    # Preserve order while dropping duplicates.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def state_dir() -> Path:
    """Per-user Wifite3 state directory (created on demand)."""
    directory = Path(os.environ.get("WIFITE3_HOME", str(Path.home() / ".wifite3")))
    directory.mkdir(parents=True, exist_ok=True)
    return directory
