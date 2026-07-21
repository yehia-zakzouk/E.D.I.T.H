"""Agent Configuration — controls how EDITH's autonomous watcher behaves.

Configured either programmatically or via CLI flags when starting ``edith watch``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class WatchMode(str, Enum):
    """What EDITH does when it detects a file change."""

    REPORT_ONLY = "report"          # Just show what could be improved (default)
    GENERATE_PATCHES = "generate"   # Generate patches, flag for user review
    AUTO_APPLY_SAFE = "auto-apply"  # Auto-apply patches that pass safety checks


@dataclass
class WatchConfig:
    """Per-directory watch configuration."""

    path: Path
    mode: WatchMode = WatchMode.REPORT_ONLY

    # File filtering
    include_extensions: tuple[str, ...] = (
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
        ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".h",
    )
    exclude_dirs: tuple[str, ...] = (
        ".git", "__pycache__", "node_modules", "venv",
        ".venv", ".env", "dist", "build", ".edith_patches",
    )
    exclude_patterns: tuple[str, ...] = (
        "*.min.*", "*.generated.*", "*.pb.*",
    )

    # Behavior
    debounce_seconds: float = 3.0           # Wait for quiet period before acting
    cooldown_seconds: float = 30.0          # Don't re-trigger on same file too fast
    max_patches_per_event: int = 5          # Don't go overboard on one change
    auto_apply_confidence: float = 0.85     # Minimum confidence for auto-apply

    # Safety
    require_review_before_apply: bool = True
    max_file_size_bytes: int = 500_000      # Skip files larger than this
    allowed_file_patterns: tuple[str, ...] = (
        "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
    )

    # Output
    patch_output_dir: Path = Path(".edith_patches/watch")


@dataclass
class AgentConfig:
    """Top-level configuration for the autonomous agent."""

    watches: list[WatchConfig] = field(default_factory=list)

    # Global settings
    daemon_pid_file: Path = Path(".edith_agent.pid")
    daemon_log_file: Path = Path(".edith_agent.log")
    max_opportunities_per_scan: int = 20

    # Notification
    verbose: bool = False
    notify_on_each_patch: bool = True
    notify_on_errors: bool = True

    # Provider reuse (avoids re-scanning the same project)
    project_cache_ttl_seconds: float = 120.0
