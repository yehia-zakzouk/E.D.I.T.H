"""DirectoryWatcher — watches a directory tree for file changes using
the ``watchdog`` library.

This is EDITH's eyes on the filesystem. Every create, modify, delete,
and rename event flows through here into the debouncer → event handler
pipeline.

Usage::

    from app.agent import DirectoryWatcher, WatchConfig, WatchMode
    from app.agent.event_handler import FileEventHandler

    config = WatchConfig(
        path=Path("backend/"),
        mode=WatchMode.GENERATE_PATCHES,
    )
    handler = FileEventHandler(config)

    watcher = DirectoryWatcher(config, handler)
    watcher.start()  # Blocks until interrupted
"""

from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.agent.config import WatchConfig, WatchMode
from app.agent.debouncer import Debouncer
from app.agent.event_handler import FileEventHandler
from app.agent.safety_guard import AutoSafetyGuard

# Watchdog may not be available in all environments
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEvent, FileSystemEventHandler

    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    FileSystemEvent = object  # type: ignore[assignment, misc]
    FileSystemEventHandler = object  # type: ignore[assignment, misc]
    Observer = None  # type: ignore[assignment, misc]


class _WatchdogHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Bridge between watchdog events and EDITH's debouncer + handler."""

    def __init__(
        self,
        config: WatchConfig,
        debouncer: Debouncer,
        handler: FileEventHandler,
        guard: AutoSafetyGuard,
    ):
        super().__init__()
        self._config = config
        self._debouncer = debouncer
        self._handler = handler
        self._guard = guard

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path.replace("\\", "/")
        if self._is_watched(path):
            self._debouncer.touch(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path.replace("\\", "/")
        if self._is_watched(path):
            self._debouncer.touch(path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = event.src_path.replace("\\", "/")
        if self._is_watched(path):
            self._handler.on_deleted(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = event.src_path.replace("\\", "/")
        dest = event.dest_path.replace("\\", "/")
        if self._is_watched(src):
            self._handler.on_deleted(src)
        if self._is_watched(dest):
            # Put the destination through the debouncer like a creation
            self._debouncer.touch(dest)

    def _is_watched(self, file_path: str) -> bool:
        """Check if this file should be watched — delegates to the safety guard."""
        allowed, _ = self._guard.can_modify(file_path)
        return allowed


class DirectoryWatcher:
    """Watches a directory tree for file changes.

    Supports two modes:

    1. **Watchdog mode** (default) — uses the ``watchdog`` library for
       efficient OS-level file system events.
    2. **Polling fallback** — periodically checks file modification times
       for environments where watchdog isn't available.

    When watchdog is used, events are passed through a Debouncer before
    reaching the FileEventHandler, so rapid save events don't trigger
    multiple improvement cycles.
    """

    def __init__(
        self,
        config: WatchConfig,
        handler: FileEventHandler,
    ):
        self._config = config
        self._handler = handler
        self._debouncer = Debouncer(quiet_window=config.debounce_seconds)
        self._observer: Optional[object] = None
        self._polling_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start watching the directory. Blocks until interrupted.

        Gracefully handles Ctrl+C and sends a shutdown notification.
        """
        if not self._config.path.exists():
            logger.error("Agent: watch path does not exist: %s", self._config.path)
            return

        print(f"\n[agent] 👁️  EDITH is watching {self._config.path.resolve()}")
        print(f"        Mode: {self._config.mode.value}")
        print(f"        Debounce: {self._config.debounce_seconds}s")
        print(f"        Extensions: {', '.join(self._config.include_extensions)}")
        print(f"        Press Ctrl+C to stop\n")

        self._running = True

        if _WATCHDOG_AVAILABLE and Observer is not None:
            self._start_watchdog()
        else:
            logger.warning("Agent: watchdog not available — falling back to polling mode")
            self._start_polling()

        # Start the debounce processing loop
        self._debounce_loop()

    def stop(self) -> None:
        """Stop the watcher gracefully."""
        self._running = False

        if self._observer is not None:
            try:
                self._observer.stop()  # type: ignore[union-attr]
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._observer = None

        print("\n[agent] Agent stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Watchdog mode
    # ------------------------------------------------------------------

    def _start_watchdog(self) -> None:
        guard = AutoSafetyGuard(self._config)
        handler = _WatchdogHandler(
            config=self._config,
            debouncer=self._debouncer,
            handler=self._handler,
            guard=guard,
        )
        self._observer = Observer()
        self._observer.schedule(  # type: ignore[union-attr]
            handler,
            str(self._config.path),
            recursive=True,
        )
        self._observer.start()  # type: ignore[union-attr]
        logger.info("Agent: watchdog observer started for %s", self._config.path)

    # ------------------------------------------------------------------
    # Polling fallback mode
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
        )
        self._polling_thread.start()

    def _polling_loop(self) -> None:
        """Polling fallback: periodically check file mtimes."""
        mtime_cache: dict[str, float] = {}

        while self._running:
            try:
                for file_path in self._walk_files():
                    try:
                        stat = Path(file_path).stat()
                        current_mtime = stat.st_mtime
                        prev_mtime = mtime_cache.get(file_path)

                        if prev_mtime is not None and current_mtime > prev_mtime:
                            self._debouncer.touch(file_path)

                        mtime_cache[file_path] = current_mtime
                    except OSError:
                        mtime_cache.pop(file_path, None)
            except Exception:
                pass

            time.sleep(1.0)  # Poll every second

    def _walk_files(self) -> list[str]:
        """Walk the watched directory and collect source files."""
        files: list[str] = []
        try:
            for root, dirs, names in os.walk(str(self._config.path)):
                # Filter excluded dirs
                dirs[:] = [d for d in dirs if d not in self._config.exclude_dirs]
                for name in names:
                    ext = Path(name).suffix.lower()
                    if ext in self._config.include_extensions:
                        files.append(os.path.join(root, name))
        except Exception:
            pass
        return files

    # ------------------------------------------------------------------
    # Debounce processing loop
    # ------------------------------------------------------------------

    def _debounce_loop(self) -> None:
        """Poll the debouncer and process ready files."""
        try:
            while self._running:
                ready = self._debouncer.pop_ready()
                for file_path in ready:
                    self._handler.on_modified(file_path)
                time.sleep(0.5)  # Check every 500ms
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
