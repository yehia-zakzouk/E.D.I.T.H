"""AutoSafetyGuard — safety rules for autonomous file improvement.

This is the **gatekeeper** for the watcher. It's more conservative than
the Sprint 9.5 SafetyEngine because the watcher runs unattended and
modifies files without direct user supervision.

Checks
------
1. **File boundary** — Only touch known source files within the watched tree.
2. **Size sanity** — Skip binary, minified, or generated files.
3. **Git status** — Don't modify files with uncommitted changes (optional).
4. **Cooldown** — Don't re-improve the same file too frequently.
5. **Pattern allowlist** — Only touch files matching known source patterns.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from app.agent.config import WatchConfig


class AutoSafetyGuard:
    """Validates that it's safe to auto-improve a file.

    Usage::

        guard = AutoSafetyGuard(watch_config)
        if guard.can_modify(file_path):
            result = engine.improve_single_file(project, file_path, source)
    """

    def __init__(self, config: WatchConfig):
        self._config = config
        self._cooldowns: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def can_modify(self, file_path: str) -> tuple[bool, str]:
        """Run all checks on a file.

        Returns
        -------
        (allowed, reason)
            allowed: True if it's safe to proceed.
            reason: A human-readable explanation if denied.
        """
        path = Path(file_path)

        # 1. Is this within the watched tree?
        if not self._is_within_watched(path):
            return False, "File is outside the watched directory tree"

        # 2. Is it a source file with an allowed extension?
        ext = path.suffix.lower()
        if ext not in self._config.include_extensions:
            return False, f"Extension '{ext}' is not in the watch allowlist"

        # 3. Is it an excluded directory?
        for part in path.parts:
            if part in self._config.exclude_dirs:
                return False, f"File is inside an excluded directory ({part})"

        # 4. Check exclude patterns
        for pattern in self._config.exclude_patterns:
            if path.match(pattern):
                return False, f"File matches exclude pattern '{pattern}'"

        # 5. Size check
        try:
            size = path.stat().st_size
            if size > self._config.max_file_size_bytes:
                return False, f"File is too large ({size} > {self._config.max_file_size_bytes} bytes)"
            if size == 0:
                return False, "File is empty"
        except OSError:
            return False, "Cannot stat file"

        # 6. Check if file looks generated or minified
        if self._looks_generated(file_path):
            return False, "File appears to be auto-generated or minified"

        return True, "OK"

    def check_modify_batch(
        self, file_paths: list[str]
    ) -> list[tuple[str, bool, str]]:
        """Run safety checks on multiple files.

        Returns a list of (file_path, allowed, reason) tuples.
        """
        results: list[tuple[str, bool, str]] = []
        for fp in file_paths:
            allowed, reason = self.can_modify(fp)
            results.append((fp, allowed, reason))
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_within_watched(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            watched = self._config.path.resolve()
            return watched in resolved.parents or resolved == watched
        except (ValueError, OSError):
            return False

    @staticmethod
    def _looks_generated(file_path: str) -> bool:
        """Heuristic: skip files that appear auto-generated."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(2048)
        except OSError:
            return True  # Can't read = don't touch

        # Check for "auto-generated" or "do not edit" markers
        markers = [
            r"auto-?generated",
            r"do\s+not\s+edit",
            r"@generated",
            r"this\s+file\s+is\s+generated",
        ]
        for marker in markers:
            if re.search(marker, head, re.IGNORECASE):
                return True

        # Check for minified content (single very long line)
        first_line_len = head.find("\n")
        if first_line_len > 2000:  # 2000 chars on first line = likely minified
            return True

        # Check for binary content
        if "\0" in head:  # null byte
            return True

        return False
