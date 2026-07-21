"""Debouncer — prevents EDITH from triggering on rapid file changes.

When a user is typing, the filesystem fires a stream of events.
The debouncer waits for a quiet period before signalling that a
change is ready to process.

Usage::

    debouncer = Debouncer(quiet_window=3.0)
    debouncer.touch("src/main.py")  # called on each file change event

    if debouncer.is_ready("src/main.py"):
        # Process the change — user stopped typing
        print(debouncer.pop_ready())
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Optional


class Debouncer:
    """Debounces file change events per file.

    Each file gets its own timer. Only once a file has been "quiet"
    for ``quiet_window`` seconds does it become ready for processing.
    """

    MAX_AGE_SECONDS = 300  # 5 minutes — evict stale entries to prevent memory leaks

    def __init__(self, quiet_window: float = 3.0):
        self._quiet_window = quiet_window
        self._last_seen: dict[str, float] = {}
        self._lock = Lock()
        self._last_eviction: float = 0.0

    def touch(self, file_path: str) -> None:
        """Record that a file changed *now*.

        Call this from the file event handler every time a file
        is created, modified, or deleted.
        """
        now = time.monotonic()
        with self._lock:
            self._last_seen[file_path] = now
            # Opportunistic eviction of stale entries
            self._evict_stale(now)

    def is_ready(self, file_path: str, now: Optional[float] = None) -> bool:
        """Check if a file has been quiet long enough to process."""
        with self._lock:
            last = self._last_seen.get(file_path)
            if last is None:
                return False
            now = now or time.monotonic()
            return (now - last) >= self._quiet_window

    def pop_ready(self, now: Optional[float] = None) -> list[str]:
        """Return all file paths that are ready for processing and remove them.

        Use this in a polling loop or on each debounce tick.
        """
        now = now or time.monotonic()
        ready: list[str] = []

        with self._lock:
            self._evict_stale(now)
            for path, last in list(self._last_seen.items()):
                if (now - last) >= self._quiet_window:
                    ready.append(path)
                    del self._last_seen[path]

        return ready

    def _evict_stale(self, now: float) -> None:
        """Remove entries that have been pending longer than MAX_AGE_SECONDS.

        This prevents unbounded memory growth when files are continuously
        being written without ever reaching the quiet window.
        """
        # Only run eviction once per second at most
        if now - self._last_eviction < 1.0:
            return
        self._last_eviction = now

        stale = [
            path
            for path, last in self._last_seen.items()
            if (now - last) >= self.MAX_AGE_SECONDS
        ]
        for path in stale:
            del self._last_seen[path]

    @property
    def pending_count(self) -> int:
        """Number of files currently being debounced."""
        with self._lock:
            return len(self._last_seen)

    def clear(self) -> None:
        """Clear all pending debouncers."""
        with self._lock:
            self._last_seen.clear()

    def cancel(self, file_path: str) -> None:
        """Remove a specific file from the debouncer."""
        with self._lock:
            self._last_seen.pop(file_path, None)
