"""FileEventHandler — processes file system change events and triggers
EDITH's autonomous improvement pipeline.

This is where the watcher connects to the Sprint 9 pipeline.

Flow
----
1. A file is created/modified/deleted
2. Debouncer waits for the quiet period
3. Event handler determines what changed and reads the file
4. Safety guard checks if the file is safe to auto-improve
5. The opportunity engine runs on the changed file
6. Safe patches are generated (and optionally applied)
7. Results are reported via the notifier
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.agent.config import WatchConfig, WatchMode
from app.agent.debouncer import Debouncer
from app.agent.safety_guard import AutoSafetyGuard
from app.agent.notifier import Notifier, ConsoleNotifier

from app.models.project import Project
from app.models.file_index import FileIndex
from app.models.file_analysis import FileAnalysis
from app.services.knowledge_extractor import KnowledgeExtractor
from app.services.scanner import RepositoryScanner
from app.services.indexer import RepositoryIndexer
from app.services.detector import ProjectDetector

from app.autonomous import AutonomousEngine, PatchStatus


class FileEventHandler:
    """Processes file system changes and triggers autonomous improvement.

    Usage::

        handler = FileEventHandler(config)
        handler.on_modified("src/main.py", current_source)

    This is called by the DirectoryWatcher after debouncing.
    """

    def __init__(
        self,
        config: WatchConfig,
        notifier: Optional[Notifier] = None,
    ):
        self._config = config
        self._notifier = notifier or ConsoleNotifier()
        self._guard = AutoSafetyGuard(config)
        self._project_cache: dict[str, tuple[Project, float]] = {}
        self._file_cache: dict[str, tuple[str, float]] = {}  # path → (source, mtime)

        # Lazy-init the autonomous engine
        self._engine: Optional[AutonomousEngine] = None
        self._scanner: Optional[RepositoryScanner] = None
        self._detector: Optional[ProjectDetector] = None
        self._indexer: Optional[RepositoryIndexer] = None
        self._extractor: Optional[KnowledgeExtractor] = None

    # ------------------------------------------------------------------
    # Public handlers
    # ------------------------------------------------------------------

    def on_modified(self, file_path: str) -> None:
        """Handle a file modification event.

        Args:
            file_path: Absolute path to the modified file.
        """
        if not self._should_process(file_path):
            return

        logger.info("Agent: processing modification: %s", file_path)

        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Agent: cannot read %s — %s", file_path, e)
            return

        self._process_change(file_path, source, "modified")

    def on_created(self, file_path: str) -> None:
        """Handle a file creation event."""
        if not self._should_process(file_path):
            return

        logger.info("Agent: processing creation: %s", file_path)

        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        self._process_change(file_path, source, "created")

    def on_deleted(self, file_path: str) -> None:
        """Handle a file deletion event.

        For deletions, EDITH just logs the event and updates its cache.
        """
        logger.info("Agent: file deleted: %s", file_path)
        self._file_cache.pop(file_path, None)

    def on_moved(self, src_path: str, dest_path: str) -> None:
        """Handle a file rename/move event."""
        logger.info("Agent: file moved: %s → %s", src_path, dest_path)
        self._file_cache.pop(src_path, None)
        if self._should_process(dest_path):
            try:
                source = Path(dest_path).read_text(encoding="utf-8", errors="replace")
                self._process_change(dest_path, source, "moved")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _should_process(self, file_path: str) -> bool:
        """Quick pre-checks before running the full pipeline."""
        # Safety guard (fast checks)
        allowed, reason = self._guard.can_modify(file_path)
        if not allowed:
            logger.debug("Agent: skipped %s — %s", file_path, reason)
            return False

        # Check cache to avoid re-processing unchanged files
        try:
            current_mtime = Path(file_path).stat().st_mtime
            cached = self._file_cache.get(file_path)
            if cached is not None:
                _, cached_mtime = cached
                if current_mtime <= cached_mtime:
                    logger.debug("Agent: skipped %s — file unchanged since last check", file_path)
                    return False
        except OSError:
            return False

        return True

    def _process_change(self, file_path: str, source: str, event_type: str) -> None:
        """Core: run the opportunity engine on a single changed file."""
        logger.debug("Agent: analyzing %s (%s)", file_path, event_type)

        # Update cache
        try:
            mtime = Path(file_path).stat().st_mtime
            self._file_cache[file_path] = (source, mtime)
        except OSError:
            pass

        # Build a mini-project context for this file
        project = self._build_mini_project(file_path, source)
        if project is None:
            return

        # ── Run the autonomous improvement pipeline ────────────────
        engine = self._get_engine()
        try:
            opportunities = engine.find_opportunities(project)
        except Exception as e:
            logger.warning("Agent: opportunity scan failed for %s: %s", file_path, e)
            self._notifier.notify_error(file_path, str(e))
            return

        if not opportunities:
            logger.debug("Agent: no opportunities in %s — file looks clean", file_path)
            return

        # Report what we found
        by_severity: dict[str, int] = {}
        for opp in opportunities:
            by_severity[opp.severity.value] = by_severity.get(opp.severity.value, 0) + 1

        severity_summary = ", ".join(f"{k}={v}" for k, v in by_severity.items())
        logger.info(
            "Agent: found %d opportunities in %s (%s)",
            len(opportunities),
            file_path,
            severity_summary,
        )

        if self._config.mode == WatchMode.REPORT_ONLY:
            # Just report — don't generate patches
            self._notifier.notify_opportunities(
                file_path, opportunities, severity_summary
            )
            return

        # ── Generate and review patches ────────────────────────────
        try:
            result = engine.improve(project)
        except Exception as e:
            logger.warning("Agent: improvement pipeline failed for %s: %s", file_path, e)
            self._notifier.notify_error(file_path, str(e))
            return

        if not result.patches:
            logger.debug("Agent: no patches generated for %s", file_path)
            return

        safe_patches = [p for p in result.patches if p.status == PatchStatus.SAFE]

        if self._config.mode == WatchMode.GENERATE_PATCHES:
            # Generate patches and notify
            self._notifier.notify_patches(
                file_path, safe_patches, result.text_report()
            )
            return

        if self._config.mode == WatchMode.AUTO_APPLY_SAFE:
            # Auto-apply safe patches with sufficient confidence
            applied = 0
            for patch in safe_patches:
                from app.autonomous.impact_predictor import ImpactPredictor
                confidence = ImpactPredictor.confidence(patch)
                if confidence >= self._config.auto_apply_confidence:
                    try:
                        Path(patch.file_path).write_text(patch.new_code, encoding="utf-8")
                        applied += 1
                        logger.info(
                            "Agent: auto-applied patch to %s (confidence=%.2f)",
                            patch.file_path,
                            confidence,
                        )
                    except Exception as e:
                        logger.warning(
                            "Agent: failed to auto-apply patch to %s: %s",
                            patch.file_path,
                            e,
                        )
                        self._notifier.notify_error(patch.file_path, str(e))

            if applied > 0:
                self._notifier.notify_auto_applied(file_path, applied)

    def _build_mini_project(self, file_path: str, source: str) -> Optional[Project]:
        """Build a minimal Project containing just the changed file.

        This avoids re-scanning the entire repo on every file change.
        """
        path = Path(file_path).resolve()
        root = self._find_project_root(path)
        if root is None:
            logger.debug("Agent: no project root found for %s", file_path)
            return None

        cache_key = str(root)
        now = time.monotonic()

        # Check cache — validate TTL
        cached = self._project_cache.get(cache_key)
        if cached is not None:
            project, cached_at = cached
            ttl = self._config.max_patches_per_event * 30.0  # ~150s default
            if now - cached_at < ttl:
                # Cache hit — build a fresh FileIndex for the changed file
                # instead of mutating the cached project
                extractor = self._get_extractor()
                try:
                    temp_fi = FileIndex(path=path)
                    temp_fi.lines = len(source.splitlines())
                    analysis = extractor.analyze_file(path, source)
                    temp_fi.analysis = analysis

                    # Create a NEW list with the updated file, keeping the rest
                    updated_files = []
                    for fi in project.indexed_files:
                        if str(fi.path) == file_path:
                            updated_files.append(temp_fi)
                        else:
                            updated_files.append(fi)
                    if not any(str(f.path) == file_path for f in updated_files):
                        updated_files.append(temp_fi)

                    # Create a lightweight copy of the project with updated files
                    # Don't mutate the cached project
                    mini_project = Project(root=root)
                    mini_project.files = project.files
                    mini_project.languages = project.languages
                    mini_project.graph = project.graph
                    mini_project.indexed_files = updated_files

                    return mini_project
                except Exception as e:
                    logger.warning("Agent: failed to analyze %s: %s", file_path, e)
                    return project  # Return the cached project as-is
            else:
                # TTL expired — remove stale entry
                self._project_cache.pop(cache_key, None)

        # Build fresh
        project = Project(root=root)
        scanner = self._get_scanner()
        detector = self._get_detector()
        indexer = self._get_indexer()
        extractor = self._get_extractor()

        try:
            project.files = scanner.scan(str(root))
            project = detector.detect(project)
            project = indexer.index(project)
            project = extractor.analyze(project)
        except Exception as e:
            logger.warning("Agent: failed to scan project %s: %s", root, e)
            return None

        self._project_cache[cache_key] = (project, now)
        return project

    @staticmethod
    def _find_project_root(path: Path) -> Optional[Path]:
        """Walk up from a file to find the project root (where .git/ lives)."""
        for parent in [path] + list(path.parents):
            if (parent / ".git").exists() or (parent / ".git").is_dir():
                return parent
            # Also check for setup.py, pyproject.toml, package.json
            for marker in ("setup.py", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"):
                if (parent / marker).exists():
                    return parent
        return None

    # ------------------------------------------------------------------
    # Lazy initializers
    # ------------------------------------------------------------------

    def _get_engine(self) -> AutonomousEngine:
        if self._engine is None:
            self._engine = AutonomousEngine(
                max_opportunities=self._config.max_patches_per_event * 4,
                use_llm=False,  # Don't use LLM in auto-mode for speed
                auto_safety_check=True,
            )
        return self._engine

    def _get_scanner(self) -> RepositoryScanner:
        if self._scanner is None:
            self._scanner = RepositoryScanner()
        return self._scanner

    def _get_detector(self) -> ProjectDetector:
        if self._detector is None:
            self._detector = ProjectDetector()
        return self._detector

    def _get_indexer(self) -> RepositoryIndexer:
        if self._indexer is None:
            self._indexer = RepositoryIndexer()
        return self._indexer

    def _get_extractor(self) -> KnowledgeExtractor:
        if self._extractor is None:
            self._extractor = KnowledgeExtractor()
        return self._extractor

    def invalidate_cache(self, project_root: Optional[str] = None) -> None:
        """Force cache refresh for a project."""
        if project_root:
            self._project_cache.pop(project_root, None)
        else:
            self._project_cache.clear()
        self._file_cache.clear()
