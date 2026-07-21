"""EDITH Autonomous Agent — Sprint 10.

EDITH evolves from a stateless analyzer into a **live autonomous agent**
that watches the filesystem, detects changes, and self-improves.

Architecture
------------
File Change Event
       │
       ▼
  Debouncer (waits for quiet period)
       │
       ▼
  Safety Guard (is this file safe to auto-improve?)
       │
       ▼
  Event Handler (determine what changed)
       │
       ▼
  Re-scan changed file(s)
       │
       ▼
  Opportunity Engine (find what to improve)
       │
       ▼
  Generate → Review → Safety Check → Predict Impact
       │
       ▼
  Report / Auto-apply (based on config)

Usage
-----
    # Start watching a directory
    edith watch backend/

    # Watch with auto-apply for safe patches
    edith watch backend/ --auto-apply

    # Stop the running watcher
    edith watch --stop
"""

from app.agent.config import AgentConfig, WatchMode, WatchConfig
from app.agent.debouncer import Debouncer
from app.agent.safety_guard import AutoSafetyGuard
from app.agent.event_handler import FileEventHandler
from app.agent.watcher import DirectoryWatcher
from app.agent.daemon import AgentDaemon
from app.agent.notifier import Notifier, ConsoleNotifier

__all__ = [
    "AgentConfig",
    "WatchMode",
    "WatchConfig",
    "Debouncer",
    "AutoSafetyGuard",
    "FileEventHandler",
    "DirectoryWatcher",
    "AgentDaemon",
    "Notifier",
    "ConsoleNotifier",
]
