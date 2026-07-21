#!/usr/bin/env python3
"""EDITH — CLI entry point that wires the full AI pipeline together.

Usage
-----
    python -m app.main scan [--force] <path>
    python -m app.main ask  [--force] <path> <question>
    python -m app.main chat [--force] <path>
    python -m app.main cache [--clear]
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

# Fix Windows console for Unicode
if os.name == "nt":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.core.config import config, logger
from app.models.project import Project
from app.services.scanner import RepositoryScanner
from app.services.detector import ProjectDetector
from app.services.indexer import RepositoryIndexer
from app.services.knowledge_extractor import KnowledgeExtractor
from app.graph.graph_builder import GraphBuilder

from app.database.database import DatabaseManager
from app.database.memory_engine import MemoryEngine as DatabaseMemoryEngine

from app.ai.openai_provider import OpenAIProvider
from app.ai.mock_provider import MockProvider
from app.ai.context_engine import ContextEngine
from app.ai.prompt_builder import PromptBuilder
from app.ai.intent_detector import IntentDetector
from app.ai.conversation_memory import ConversationMemory

from app.review.review_engine import ReviewEngine
from app.review.analyzers.architecture import ArchitectureAnalyzer
from app.review.visualizer import CouplingGraphVisualizer

from app.history.history_engine import HistoryEngine
from app.history.trend_analyzer import TrendAnalyzer
from app.dashboard.repository_health import RepositoryHealth
from app.dashboard.timeline import Timeline
from app.dashboard.metrics import compute_aggregates
from app.learning.knowledge_base import KnowledgeBase
from app.learning.pattern_engine import PatternEngine
from app.learning.recommendation_memory import RecommendationMemory

from app.autonomous import AutonomousEngine, ImprovementResult, PatchStatus

from app.agent import AgentConfig, WatchConfig, WatchMode, DirectoryWatcher, FileEventHandler, ConsoleNotifier, AgentDaemon


# ------------------------------------------------------------------
# Persistent cache — three-tier: in-memory → SQLite → full scan
# ------------------------------------------------------------------

_db_manager: DatabaseManager | None = None
_db_memory: DatabaseMemoryEngine | None = None
_in_memory_cache: dict[str, Project] = {}


def _get_db() -> tuple[DatabaseManager, DatabaseMemoryEngine]:
    """Lazy-init the database connection and memory engine singleton."""
    global _db_manager, _db_memory
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.initialize()
    if _db_memory is None:
        _db_memory = DatabaseMemoryEngine(_db_manager.connection)
    return _db_manager, _db_memory


def scan_repository(root: Path, force: bool = False) -> Project:
    """Run the full analysis pipeline with a three-tier cache.

    Cache hierarchy
    ---------------
    1. **In-memory** — fastest, lives for the process lifetime
    2. **SQLite**    — persists between sessions via ``database/MemoryEngine``
    3. **Full scan** — runs the scanner, detector, indexer, and extractor
    """
    key = str(root.resolve())

    # Tier 1 — in-memory
    if not force and key in _in_memory_cache:
        logger.debug("Cache TIER-1 hit for %s", key)
        return _in_memory_cache[key]

    # Tier 2 — SQLite
    if not force:
        try:
            _, db_memory = _get_db()
            cached = db_memory.load(key)
            if cached is not None:
                logger.debug("Cache TIER-2 hit for %s", key)
                # Rebuild the graph — MemoryEngine.load() doesn't restore it
                cached = GraphBuilder().build(cached)
                _in_memory_cache[key] = cached
                return cached
        except Exception:
            logger.debug("Cache TIER-2 miss (or error) for %s", key)

    # Tier 3 — full scan
    logger.info("Full scan for %s", root)
    project = Project(root=root)

    scanner = RepositoryScanner()
    detector = ProjectDetector()
    indexer = RepositoryIndexer()
    extractor = KnowledgeExtractor()

    print("[scan] Scanning...")
    project.files = scanner.scan(str(root))
    print(f"       Found {len(project.files)} files")

    print("[scan] Detecting technologies...")
    project = detector.detect(project)
    print(f"       Languages: {project.languages}")

    print("[scan] Indexing...")
    project = indexer.index(project)
    print(f"       Indexed {len(project.indexed_files)} files")

    print("[scan] Extracting knowledge...")
    project = extractor.analyze(project)
    print(f"       Symbols: {sum(len(f.analysis.symbols) if f.analysis else 0 for f in project.indexed_files)}")
    print(f"       Graph: {len(project.graph.nodes)} nodes, {len(project.graph.edges)} edges")

    # Persist to both caches
    _in_memory_cache[key] = project
    try:
        _, db_memory = _get_db()
        db_memory.save(project)
        logger.debug("Persisted project to SQLite")
    except Exception:
        logger.exception("Failed to persist project to SQLite (non-fatal)")

    return project


def list_cached_projects() -> list[dict]:
    """Return a summary of all projects in the SQLite cache."""
    try:
        from app.database.repositories.project_repository import ProjectRepository
        _, db_memory = _get_db()
        repo = ProjectRepository(db_memory.project_repo.connection)
        cursor = repo.get_cursor()
        cursor.execute(
            "SELECT id, name, path, last_scan FROM projects ORDER BY last_scan DESC"
        )
        rows = cursor.fetchall()
        return [
            {"id": r["id"], "name": r["name"], "path": r["path"], "last_scan": r["last_scan"]}
            for r in rows
        ]
    except Exception:
        return []


def create_provider() -> OpenAIProvider | MockProvider:
    """Create the default AI provider (OpenAI if key is set, else mock)."""
    api_key = config.ai.api_key
    if not api_key:
        print("[edith] No API key configured. Set EDITH_AI__API_KEY or create .env")
        print("       EDITH will use a mock provider for testing.\n")
        return MockProvider()
    return OpenAIProvider()


# ------------------------------------------------------------------
# CLI commands
# ------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> None:
    """Scan and analyze a repository, printing a summary."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    project = scan_repository(root, force=args.force)
    print(f"\n[ok] Analysis complete for {root.name}")
    print(f"     Files: {len(project.indexed_files)}")
    print(f"     Languages: {project.languages}")
    if project.graph:
        print(f"     Graph: {len(project.graph.nodes)} nodes, {len(project.graph.edges)} edges")


def cmd_ask(args: argparse.Namespace) -> None:
    """Ask a single question about a repository."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    question = args.question
    project = scan_repository(root, force=args.force)
    provider = create_provider()
    engine = ContextEngine()
    builder = PromptBuilder()

    print("\n[edith] Building context...")
    context = engine.build_context(question, project)
    print(f"       {context['summary']}")

    print("[edith] Asking EDITH...\n")
    prompt = builder.build(question, context, project)
    answer = provider.ask(prompt)
    print(answer)


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive chat session with conversation memory."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    project = scan_repository(root, force=args.force)
    provider = create_provider()
    memory = ConversationMemory()
    engine = ContextEngine(memory=memory)
    builder = PromptBuilder()
    detector = IntentDetector()

    print("\n[edith] Chat session started — type your questions (or 'quit' to exit)\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break

        intent, target = detector.detect(question)
        context = engine.build_context(question, project, intent=intent, target=target)
        prompt = builder.build(question, context, project)

        print(f"\n[edith] Intent: {intent.value}" + (f" | Target: {target}" if target else ""))
        print("EDITH:\n")

        answer = provider.ask(prompt)
        print(answer)
        print()

        memory.add_turn(question, answer, intent=intent.value, entities=[target] if target else [])


def cmd_review(args: argparse.Namespace) -> None:
    """Run a full engineering review on a repository."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    print(f"\n[review] Analysing {root.name}...")
    project = scan_repository(root, force=args.force)

    print("[review] Running engineering review...\n")
    engine = ReviewEngine(use_llm=args.llm)
    report = engine.review(project)

    if args.json:
        import json
        json_output = json.dumps(report.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(json_output, encoding="utf-8")
            print(f"[review] JSON written to {args.output}")
        else:
            print(json_output)
    else:
        print(report.text)
        # Save text report to file if --output given without --json
        if args.output:
            Path(args.output).write_text(report.text, encoding="utf-8")
            print(f"[review] Report saved to {args.output}")

    # If LLM was used, show the enhanced section
    if args.llm:
        print("\n[review] Review enhanced with AI insights.")

    # ── Save to history ────────────────────────────────────────────
    try:
        history = HistoryEngine()
        d = report.to_dict()
        dims = {dim["name"]: dim["score"] for dim in d.get("dimensions", [])}
        history.save_review(
            project_path=str(root),
            project_name=root.name,
            overall_score=report.score.overall,
            dimension_scores=dims,
            strengths=report.score.strengths,
            weaknesses=report.score.weaknesses,
            recommendations=report.recommendations,
            metrics=d.get("metrics"),
        )
        print(f"[history] Review saved (total: {history.get_history_count()})")
    except Exception as e:
        logger.debug("Failed to save review history: %s", e)

    # ── Visualization ──────────────────────────────────────────────
    if args.visualize:
        output_path = f"coupling_{root.name}.html"
        print(f"[review] Building coupling graph...")

        arch = ArchitectureAnalyzer()
        nodes, edges = arch.get_coupling_graph(project)
        viz = CouplingGraphVisualizer()
        saved = viz.save(root.name, nodes, edges, output_path)

        print(f"[review] Coupling graph written to {saved}")

        try:
            import webbrowser
            webbrowser.open(str(saved))
        except Exception:
            pass

    print(f"[review] Complete — score: {report.score.overall}/100\n")


def cmd_history(args: argparse.Namespace) -> None:
    """Show review history for a project (Sprint 8.1)."""
    path = args.path
    history = HistoryEngine()
    reviews = history.get_recent_reviews(project_path=path, limit=args.limit)
    if not reviews:
        print(f"[history] No reviews found{' for ' + path if path else ''}.")
        return
    print(f"\n[history] {len(reviews)} review(s) found{' for ' + path if path else ''}:\n")
    for r in reviews:
        print(f"  [{r.timestamp[:16]}]  Score: {r.overall_score:.0f}/100  "
              f"Cpx:{r.complexity:.0f}  Mnt:{r.maintainability:.0f}  "
              f"Rdb:{r.readability:.0f}  Arch:{r.architecture:.0f}  "
              f"Doc:{r.documentation:.0f}  Files:{r.total_files}")


def cmd_health(args: argparse.Namespace) -> None:
    """Show repository health dashboard (Sprint 8.7)."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        return
    history = HistoryEngine()
    health = RepositoryHealth(history.review_history, history.decision_history)
    print(health.dashboard_text(str(root)))


def cmd_trends(args: argparse.Namespace) -> None:
    """Show review trends for a project (Sprint 8.2)."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        return
    history = HistoryEngine()
    report = history.get_trends(str(root))
    print(report.text())


def cmd_timeline(args: argparse.Namespace) -> None:
    """Show repository evolution timeline (Sprint 8.8)."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        return
    history = HistoryEngine()
    timeline = Timeline(history.review_history, history.decision_history)
    report = timeline.build(str(root))
    print(report.text())


def cmd_knowledge(args: argparse.Namespace) -> None:
    """Show EDITH's engineering knowledge base (Sprint 8.4)."""
    history = HistoryEngine()
    kb = KnowledgeBase(history.review_history.conn)

    if args.topic:
        summary = kb.get_topic_summary(args.topic)
        print(f"\n[knowledge] Topic: {summary['topic']}")
        print(f"  Entries: {summary['entries']}")
        print(f"  Avg confidence: {summary.get('average_confidence', 0)}")
        for obs in summary.get("observations", []):
            print(f"  • {obs['observation']} (conf={obs['confidence']}, samples={obs['samples']})")
    else:
        topics = kb.get_topics()
        if not topics:
            print("[knowledge] No knowledge accumulated yet. Run reviews to build knowledge.")
            return
        print(f"\n[knowledge] {len(topics)} topics:\n")
        for topic in topics:
            summary = kb.get_topic_summary(topic)
            print(f"  {topic:25s}  {summary['entries']} entries, "
                  f"confidence: {summary.get('average_confidence', 0)}")


def cmd_find_opportunities(args: argparse.Namespace) -> None:
    """Find improvement opportunities in a repository (Sprint 9.1)."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    print(f"\n[autonomous] Scanning {root.name} for improvement opportunities...")
    project = scan_repository(root, force=args.force)

    engine = AutonomousEngine(max_opportunities=args.max)
    opportunities = engine.find_opportunities(project)

    if not opportunities:
        print("\n[autonomous] No opportunities found — the code looks clean!")
        return

    print(f"\n[autonomous] Found {len(opportunities)} opportunities:\n")
    for opp in opportunities:
        severity_mark = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }.get(opp.severity.value, "⚪")
        print(f"  {severity_mark}  [{opp.severity.value.upper():8s}] {opp.type.value}")
        print(f"       {opp.file_path}:{opp.line}")
        print(f"       {opp.description}")
        if opp.current_value is not None:
            print(f"       Value: {opp.current_value}")
        print(f"       {opp.recommendation}")
        print()


def cmd_improve(args: argparse.Namespace) -> None:
    """Autonomously improve a repository (Sprint 9.1–9.6)."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}")
        sys.exit(1)

    print(f"\n[autonomous] Starting autonomous improvement for {root.name}...")
    project = scan_repository(root, force=args.force)

    print("[autonomous] Running full improvement pipeline...\n")
    engine = AutonomousEngine(
        use_llm=not args.no_llm,
        auto_safety_check=not args.no_safety,
    )
    result = engine.improve(project)

    # ── Print report ───────────────────────────────────────────────
    print(result.text_report())

    # ── Save patches to files ──────────────────────────────────────
    if result.patches and args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        from app.autonomous.patch_generator import PatchGenerator

        saved = 0
        for patch in result.patches:
            if patch.status in (PatchStatus.SAFE, PatchStatus.IMPROVES):
                patch_path = PatchGenerator.save_patch_file(patch, output_dir)
                saved += 1
                logger.debug("Saved patch: %s", patch_path)

        if saved > 0:
            print(f"\n[autonomous] {saved} patch(es) saved to {output_dir}/")
            print(f"            Apply with: git apply {output_dir}/*.patch")

    # ── Save to history ────────────────────────────────────────────
    try:
        from app.history.history_engine import HistoryEngine
        history = HistoryEngine()
        d = result.to_dict()
        history.save_improvement(
            project_path=str(root),
            project_name=root.name,
            opportunities_found=result.total_opportunities,
            patches_generated=result.total_patches_generated,
            patches_safe=result.total_safe_patches,
            score_before=result.overall_score_before,
            score_after=result.overall_score_after,
            details=d,
        )
        print(f"[history] Improvement saved")
    except Exception as e:
        logger.debug("Failed to save improvement history: %s", e)

    print(f"\n[autonomous] Done — {result.total_safe_patches} safe patch(es) available")


def cmd_watch(args: argparse.Namespace) -> None:
    """Watch a directory for file changes and autonomously improve.

    This is EDITH's autonomous agent mode — it watches the filesystem,
    detects changes, and triggers the improvement pipeline.
    """
    if args.stop:
        # Stop the running daemon
        agent_config = AgentConfig()
        if AgentDaemon.is_running(agent_config.daemon_pid_file):
            AgentDaemon.stop_daemon(agent_config.daemon_pid_file)
        else:
            print("[agent] No running agent found.")
        return

    if args.path is None:
        print("[agent] Usage: edith watch <path> [--mode report|generate|auto-apply]")
        print("       edith watch --stop")
        return

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"[error] Path does not exist: {path}")
        sys.exit(1)

    # Parse extensions
    if args.extensions:
        extensions = tuple(f".{ext.strip().lstrip('.')}" for ext in args.extensions.split(","))
    else:
        extensions = (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp")

    # Build the watch config
    watch_config = WatchConfig(
        path=path,
        mode=WatchMode(args.mode),
        include_extensions=extensions,
        debounce_seconds=args.debounce,
    )

    agent_config = AgentConfig(watches=[watch_config])

    # Check if already running
    if AgentDaemon.is_running(agent_config.daemon_pid_file):
        print(f"[agent] Agent is already running (PID: {agent_config.daemon_pid_file.read_text().strip()})")
        print("       Use `edith watch --stop` to stop it first.")
        return

    print(f"\n[agent] Starting EDITH autonomous watcher for: {path}")
    print(f"[agent] Mode: {args.mode}")
    print(f"[agent] Watching {len(extensions)} file types: {', '.join(sorted(extensions)[:8])}...")
    print()

    # Run the daemon
    daemon = AgentDaemon(agent_config)

    if args.background:
        if daemon.start_background():
            print(f"[agent] Agent running in background (PID file: {agent_config.daemon_pid_file})")
            print(f"[agent] Log file: {agent_config.daemon_log_file}")
        else:
            print("[agent] Falling back to foreground mode...")
            daemon.run()
    else:
        daemon.run()


def cmd_cache(args: argparse.Namespace) -> None:
    """List cached projects in the SQLite database."""
    projects = list_cached_projects()
    if not projects:
        print("[cache] No cached projects found.")
        return
    print(f"[cache] {len(projects)} cached project(s):\n")
    for p in projects:
        print(f"  [{p['id']}] {p['name']}")
        print(f"       Path: {p['path']}")
        print(f"       Last scanned: {p['last_scan']}")
        print()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="EDITH — AI-Powered Code Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Scan and analyze a repository")
    p_scan.add_argument("path", type=str, help="Path to the repository root")
    p_scan.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question about a repository")
    p_ask.add_argument("path", type=str, help="Path to the repository root")
    p_ask.add_argument("question", type=str, help="Your question")
    p_ask.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")

    # chat
    p_chat = sub.add_parser("chat", help="Interactive Q&A chat")
    p_chat.add_argument("path", type=str, help="Path to the repository root")
    p_chat.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")

    # review
    p_review = sub.add_parser("review", help="Run a full engineering review")
    p_review.add_argument("path", type=str, help="Path to the repository root")
    p_review.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")
    p_review.add_argument("--llm", action="store_true", help="Enhance review with AI interpretation")
    p_review.add_argument("--json", action="store_true", help="Output structured JSON")
    p_review.add_argument("--visualize", action="store_true", help="Generate interactive coupling graph HTML")
    p_review.add_argument("--output", type=str, default=None, help="Output path for HTML/JSON file")

    # history / sprint 8 commands
    p_history = sub.add_parser("history", help="Show review history for a project")
    p_history.add_argument("path", type=str, nargs="?", default=None, help="Project path (optional — shows all)")
    p_history.add_argument("--limit", type=int, default=10, help="Number of entries to show")

    p_health = sub.add_parser("health", help="Show repository health dashboard")
    p_health.add_argument("path", type=str, help="Project path")

    p_trends = sub.add_parser("trends", help="Show review trends for a project")
    p_trends.add_argument("path", type=str, help="Project path")

    p_timeline = sub.add_parser("timeline", help="Show repository evolution timeline")
    p_timeline.add_argument("path", type=str, help="Project path")

    p_knowledge = sub.add_parser("knowledge", help="Show EDITH's engineering knowledge")
    p_knowledge.add_argument("topic", type=str, nargs="?", default=None, help="Optional topic to filter by")

    # cache
    # autonomous / sprint 9
    p_opportunities = sub.add_parser("find-opportunities", help="Find improvement opportunities in a repository")
    p_opportunities.add_argument("path", type=str, help="Path to the repository root")
    p_opportunities.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")
    p_opportunities.add_argument("--max", type=int, default=30, help="Max opportunities to find")

    p_improve = sub.add_parser("improve", help="Autonomously improve a repository")
    p_improve.add_argument("path", type=str, help="Path to the repository root")
    p_improve.add_argument("--force", action="store_true", help="Force re-scan, ignoring cache")
    p_improve.add_argument("--no-llm", action="store_true", help="Disable LLM-based refactoring")
    p_improve.add_argument("--output-dir", type=str, default=".edith_patches", help="Directory to save patch files")
    p_improve.add_argument("--no-safety", action="store_true", help="Skip safety checks (not recommended)")

    # agent / sprint 10
    p_watch = sub.add_parser("watch", help="Watch a directory for changes and auto-improve")
    p_watch.add_argument("path", type=str, nargs="?", default=None, help="Path to watch (omit to check status or stop)")
    p_watch.add_argument("--mode", type=str, default="report", choices=["report", "generate", "auto-apply"],
                         help="Watch mode: report (default), generate patches, or auto-apply safe patches")
    p_watch.add_argument("--debounce", type=float, default=3.0, help="Debounce window in seconds")
    p_watch.add_argument("--extensions", type=str, default="",
                         help="Comma-separated extensions to watch (default: .py,.js,.ts,.go,.rs,.java)")
    p_watch.add_argument("--stop", action="store_true", help="Stop the running watcher")
    p_watch.add_argument("--background", action="store_true", help="Run in background (daemonize — Unix only)")

    # cache
    p_cache = sub.add_parser("cache", help="List cached projects")
    p_cache.add_argument("--clear", action="store_true", help="Clear all cached projects")

    args = parser.parse_args()

    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "health":
        cmd_health(args)
    elif args.command == "trends":
        cmd_trends(args)
    elif args.command == "timeline":
        cmd_timeline(args)
    elif args.command == "knowledge":
        cmd_knowledge(args)
    elif args.command == "find-opportunities":
        cmd_find_opportunities(args)
    elif args.command == "improve":
        cmd_improve(args)
    elif args.command == "watch":
        cmd_watch(args)
    elif args.command == "cache":
        if args.clear:
            from app.database.repositories.project_repository import ProjectRepository
            _, db_memory = _get_db()
            repo = ProjectRepository(db_memory.project_repo.connection)
            cursor = repo.get_cursor()
            cursor.execute("DELETE FROM projects")
            db_memory.project_repo.connection.commit()
            print("[cache] All cached projects cleared.")
        else:
            cmd_cache(args)


if __name__ == "__main__":
    main()
