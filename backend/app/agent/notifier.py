"""Notifier — reports autonomous agent activity to the user.

In a terminal environment, notifications are formatted console messages.
In a desktop environment, these could map to native OS notifications.

The notifier is pluggable — implement ``Notifier`` to support different
output channels (GUI, websocket, Slack, etc.).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from app.autonomous.models import Opportunity, Patch


def _supports_ansi() -> bool:
    """Check if the terminal supports ANSI escape codes.

    On Windows, modern terminals (Windows 10+ console, PowerShell,
    VSCode integrated terminal) support ANSI. Older Windows CMD does not.
    """
    if os.name == "nt":
        # Check for environment variables that indicate modern terminal support
        if os.environ.get("WT_SESSION"):  # Windows Terminal
            return True
        if os.environ.get("TERM_PROGRAM") in ("vscode", "hyper"):
            return True
        if os.environ.get("ANSICON") is not None:
            return True
        # Check for ANSI support via GetConsoleMode (heuristic: most modern
        # Windows terminals support it by default)
        return os.environ.get("TERM") not in (None, "")
    return True


class Notifier(ABC):
    """Abstract base for agent notifications."""

    @abstractmethod
    def notify_opportunities(
        self,
        file_path: str,
        opportunities: list[Opportunity],
        summary: str,
    ) -> None:
        ...

    @abstractmethod
    def notify_patches(
        self,
        file_path: str,
        patches: list[Patch],
        report: str,
    ) -> None:
        ...

    @abstractmethod
    def notify_auto_applied(self, file_path: str, count: int) -> None:
        ...

    @abstractmethod
    def notify_error(self, file_path: str, error: str) -> None:
        ...

    @abstractmethod
    def notify_status(self, message: str) -> None:
        ...


class ConsoleNotifier(Notifier):
    """Terminal-based notifier — prints to stdout with colors and formatting."""

    # ANSI color codes
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    def __init__(self, verbose: bool = False):
        self._verbose = verbose
        self._use_color = _supports_ansi()

    def _c(self, code: str, text: str) -> str:
        """Wrap text in ANSI color code if the terminal supports it."""
        if self._use_color and code:
            return f"{code}{text}{self.RESET}"
        return text

    def _hline(self, char: str = "━", length: int = 40) -> str:
        return char * length

    def notify_opportunities(
        self,
        file_path: str,
        opportunities: list[Opportunity],
        summary: str,
    ) -> None:
        """Print found opportunities as a compact terminal card."""
        print(f"\n{self._c(self.BLUE, '━━━ EDITH Agent — Opportunities Found ━━━')}")
        print(f"  {self._c(self.BOLD, 'File:')} {file_path}")

        # Group by severity
        critical = [o for o in opportunities if o.severity.value == "critical"]
        high = [o for o in opportunities if o.severity.value == "high"]
        medium = [o for o in opportunities if o.severity.value == "medium"]
        low = [o for o in opportunities if o.severity.value == "low"]

        if critical:
            print(f"  {self._c(self.RED, '🔴 Critical:')} {len(critical)}")
            if self._verbose:
                for o in critical[:3]:
                    print(f"    • {o.description}")

        if high:
            print(f"  {self._c(self.YELLOW, '🟠 High:')} {len(high)}")
            if self._verbose:
                for o in high[:3]:
                    print(f"    • {o.description}")

        if medium:
            print(f"  {self._c(self.YELLOW, '🟡 Medium:')} {len(medium)}")
            if self._verbose:
                for o in medium[:3]:
                    print(f"    • {o.description}")

        if low:
            print(f"  {self._c(self.GREEN, '🟢 Low:')} {len(low)}")
            if self._verbose:
                for o in low[:3]:
                    print(f"    • {o.description}")

        # Filter out INFO severity for cleaner output
        info_count = len([o for o in opportunities if o.severity.value == "info"])
        if info_count:
            print(f"  {self._c(self.DIM, f'Info: {info_count}')}")

        print(f"  {self._c(self.BOLD, 'Summary:')} {summary}")
        print(f"{self._c(self.BLUE, self._hline())}")

    def notify_patches(
        self,
        file_path: str,
        patches: list[Patch],
        report: str,
    ) -> None:
        """Print generated patch information."""
        print(f"\n{self._c(self.CYAN, '━━━ EDITH Agent — Patches Generated ━━━')}")
        print(f"  {self._c(self.BOLD, 'File:')} {file_path}")
        print(f"  {self._c(self.BOLD, 'Patches:')} {len(patches)}")

        if len(patches) < 3:
            # Show patch details inline
            for i, patch in enumerate(patches):
                added = patch.diff_lines_added
                removed = patch.diff_lines_removed
                delta = patch.score_delta or 0.0
                status = patch.status.value
                sign = "+" if delta > 0 else ""
                print(f"\n  {self._c(self.BOLD, f'Patch {i+1}:')} "
                      f"{patch.file_path.split('/')[-1]}"
                      f"  {sign}{delta:.1f} pts  "
                      f"+{added}/-{removed} lines  "
                      f"[{status}]")
        else:
            print(f"  (use `edith improve` to see full details)")

        # Show the report summary
        report_lines = report.split("\n")
        for line in report_lines[:8]:  # First 8 lines
            print(f"  {line}")
        print(f"{self._c(self.CYAN, self._hline())}")

    def notify_auto_applied(self, file_path: str, count: int) -> None:
        """Print auto-apply confirmation."""
        print(f"\n{self._c(self.GREEN, '━━━ EDITH Agent — Auto-Applied ━━━')}")
        print(f"  {self._c(self.BOLD, 'File:')} {file_path}")
        print(f"  {self._c(self.BOLD, 'Applied:')} {count} patch(es)")
        print(f"  {self._c(self.GREEN, '✓')} All changes passed safety checks")
        print(f"{self._c(self.GREEN, self._hline())}")

    def notify_error(self, file_path: str, error: str) -> None:
        """Print an error notification."""
        print(f"\n{self._c(self.RED, '━━━ EDITH Agent — Error ━━━')}")
        print(f"  {self._c(self.BOLD, 'File:')} {file_path}")
        print(f"  {self._c(self.BOLD, 'Error:')} {error}")
        print(f"{self._c(self.RED, self._hline())}")

    def notify_status(self, message: str) -> None:
        """Print a status message."""
        print(f"\n{self._c(self.BLUE, '[agent]')} {message}")
