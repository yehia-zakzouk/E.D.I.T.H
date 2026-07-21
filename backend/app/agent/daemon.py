"""AgentDaemon — background daemon that runs EDITH's autonomous watcher.

This orchestrates the full lifecycle:

1. **Start** — Initialize the watcher with its config
2. **Run** — Watch for file changes, trigger improvement pipeline
3. **Stop** — Gracefully shut down the watcher

Supports both foreground and background daemon modes.

Usage::

    # Foreground (blocks)
    daemon = AgentDaemon(config)
    daemon.run()

    # Background (daemonizes)
    daemon.start_background()
    ...

    daemon.stop()
"""

from __future__ import annotations

import atexit
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from app.core.config import config as app_config, logger
from app.agent.config import AgentConfig, WatchConfig, WatchMode
from app.agent.watcher import DirectoryWatcher
from app.agent.event_handler import FileEventHandler
from app.agent.notifier import ConsoleNotifier


class AgentDaemon:
    """Orchestrates EDITH's autonomous agent lifecycle.

    This is the top-level controller that ties together the watcher,
    event handler, and notifier.

    Usage::

        daemon = AgentDaemon(config)
        daemon.run()  # Blocks until Ctrl+C
    """

    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self._config = agent_config or AgentConfig()
        self._notifier = ConsoleNotifier(verbose=self._config.verbose)
        self._watchers: list[DirectoryWatcher] = []
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start all watchers and block until interrupted.

        This is the main entry point for both foreground and
        background daemon modes.
        """
        if not self._config.watches:
            self._notifier.notify_status(
                "No directories configured to watch. "
                "Use `edith watch <path>` to add one."
            )
            return

        self._running = True
        self._setup_signal_handlers()

        # Register shutdown on exit
        atexit.register(self.stop)

        # Start all watchers
        for watch_config in self._config.watches:
            handler = FileEventHandler(watch_config, notifier=self._notifier)
            watcher = DirectoryWatcher(watch_config, handler)
            self._watchers.append(watcher)
            # Each watcher runs in its own thread
            import threading
            t = threading.Thread(target=watcher.start, daemon=True)
            t.start()

        print(f"\n[daemon] EDITH Agent is running — watching {len(self._config.watches)} path(s)")
        print(f"[daemon] PID: {os.getpid()}")
        print(f"[daemon] Press Ctrl+C to stop\n")

        try:
            # Keep the main thread alive
            while self._running:
                time.sleep(1)

                # Report status periodically
                for watcher in self._watchers:
                    if not watcher.is_running:
                        logger.warning("Agent: a watcher has stopped unexpectedly")
                        self._running = False
                        break

        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop all watchers gracefully."""
        if not self._running:
            return

        self._running = False
        for watcher in self._watchers:
            try:
                watcher.stop()
            except Exception:
                pass
        self._watchers.clear()

        # Clean up PID file
        pid_file = self._config.daemon_pid_file
        if pid_file.exists():
            try:
                pid_file.unlink()
            except OSError:
                pass

        print("\n[daemon] Agent stopped.")

    def start_background(self) -> bool:
        """Daemonize the agent process (Unix only).

        On Windows, falls back to foreground mode and warns the user.

        Returns True if daemonization succeeded.
        """
        if os.name == "nt":
            print("[daemon] Background mode is not supported on Windows.")
            print("[daemon] Use `edith watch` in foreground mode instead.")
            return False

        try:
            pid = os.fork()
            if pid > 0:
                # Parent process — write PID and exit
                pid_file = self._config.daemon_pid_file
                pid_file.write_text(str(pid), encoding="utf-8")
                print(f"[daemon] Agent started in background (PID: {pid})")
                print(f"[daemon] To stop: kill {pid}")
                return True
        except OSError as e:
            logger.error("Agent: fork failed: %s", e)
            return False

        # Child process — run the watcher
        self._config.daemon_pid_file.write_text(str(os.getpid()), encoding="utf-8")

        # Redirect output to log file
        log_file = self._config.daemon_log_file
        try:
            sys.stdout = open(log_file, "a", encoding="utf-8")
            sys.stderr = sys.stdout
        except OSError:
            pass

        self.run()
        return True

    @staticmethod
    def is_running(pid_file: Path) -> bool:
        """Check if a daemon is already running by reading its PID file."""
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            # Check if process exists
            os.kill(pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            return False

    @staticmethod
    def stop_daemon(pid_file: Path) -> bool:
        """Stop a running daemon by PID.

        Returns True if the daemon was stopped.
        """
        if not pid_file.exists():
            print("[daemon] No PID file found — is the agent running?")
            return False
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink()
            print(f"[daemon] Agent (PID: {pid}) stopped.")
            return True
        except (ValueError, OSError, ProcessLookupError) as e:
            print(f"[daemon] Could not stop agent: {e}")
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _setup_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            pass  # Some signals may not be available on Windows

    def _handle_signal(self, signum: int, frame) -> None:  # type: ignore[no-untyped-def]
        logger.info("Agent: received signal %d — shutting down", signum)
        self.stop()
