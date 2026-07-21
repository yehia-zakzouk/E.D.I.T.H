"""EDITH Web API — FastAPI server that powers the desktop UI.

Run with::

    uvicorn app.api:app --reload --port 8765
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
from app.review.scoring import ReviewScore
from app.autonomous import AutonomousEngine

from app.llm import ProviderFactory, LLMConfig
from app.llm.config import llm_config as llm_settings


# ---------------------------------------------------------------------------
# Global state (singletons shared across requests)
# ---------------------------------------------------------------------------

_db_manager: DatabaseManager | None = None
_db_memory: DatabaseMemoryEngine | None = None
_in_memory_cache: dict[str, Project] = {}


def _get_db() -> tuple[DatabaseManager, DatabaseMemoryEngine]:
    global _db_manager, _db_memory
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.initialize()
    if _db_memory is None:
        _db_memory = DatabaseMemoryEngine(_db_manager.connection)
    return _db_manager, _db_memory


def _get_or_scan_project(root: Path, force: bool = False) -> Project:
    """Three-tier cache: in-memory → SQLite → full scan."""
    key = str(root.resolve())

    if not force and key in _in_memory_cache:
        return _in_memory_cache[key]

    if not force:
        try:
            _, db_memory = _get_db()
            cached = db_memory.load(key)
            if cached is not None:
                cached = GraphBuilder().build(cached)
                _in_memory_cache[key] = cached
                return cached
        except Exception:
            pass

    logger.info("Full scan for %s", root)
    project = Project(root=root)
    project.files = RepositoryScanner().scan(str(root))
    project = ProjectDetector().detect(project)
    project = RepositoryIndexer().index(project)
    project = KnowledgeExtractor().analyze(project)

    _in_memory_cache[key] = project
    try:
        _, db_memory = _get_db()
        db_memory.save(project)
    except Exception:
        logger.exception("Failed to persist to SQLite (non-fatal)")

    return project


def _get_provider():
    """Get the LLM provider for chat / streaming.

    Uses ProviderFactory (reads EDITH_LLM__PROVIDER) as the primary
    path. Falls back to MockProvider only when the factory fails
    (e.g. when neither LLM config nor old AI config has credentials).
    """
    try:
        return ProviderFactory.create()
    except Exception as e:
        logger.warning("ProviderFactory failed: %s — falling back to mock", e)
    from app.ai.mock_provider import MockProvider
    return MockProvider()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EDITH API starting")
    yield
    logger.info("EDITH API shutting down")


app = FastAPI(
    title="EDITH API",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Static files (the single-page frontend)
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main HTML page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>EDITH — frontend not built yet</h1>")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    path: str
    force: bool = False


class AskRequest(BaseModel):
    path: str
    question: str
    force: bool = False


class ProjectSummary(BaseModel):
    id: int | None = None
    name: str
    root: str
    languages: list[str] = []
    frameworks: list[str] = []
    file_count: int = 0
    symbol_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    cached: bool = False


def _project_to_summary(p: Project, cached: bool = False) -> dict:
    return {
        "id": p.id,
        "name": p.root.name,
        "root": str(p.root),
        "languages": p.languages,
        "frameworks": p.frameworks,
        "file_count": len(p.indexed_files),
        "symbol_count": sum(
            len(f.analysis.symbols) if f.analysis else 0 for f in p.indexed_files
        ),
        "node_count": len(p.graph.nodes) if p.graph else 0,
        "edge_count": len(p.graph.edges) if p.graph else 0,
        "cached": cached,
    }


@app.post("/scan", response_model=ProjectSummary)
async def scan(req: ScanRequest):
    root = Path(req.path).resolve()
    if not root.exists():
        raise HTTPException(400, f"Path does not exist: {root}")
    project = _get_or_scan_project(root, force=req.force)
    cached = str(root.resolve()) in _in_memory_cache and not req.force
    return _project_to_summary(project, cached=cached)


@app.post("/ask")
async def ask(req: AskRequest):
    root = Path(req.path).resolve()
    if not root.exists():
        raise HTTPException(400, f"Path does not exist: {root}")

    project = _get_or_scan_project(root, force=req.force)
    provider = _get_provider()
    engine = ContextEngine()
    builder = PromptBuilder()

    context = engine.build_context(req.question, project)
    prompt = builder.build(req.question, context, project)
    answer = provider.ask(prompt)

    return {
        "question": req.question,
        "answer": answer,
        "context_summary": context.get("summary", ""),
    }


class GraphData(BaseModel):
    nodes: list[dict]
    edges: list[dict]


@app.get("/project/graph", response_model=GraphData)
async def get_graph(path: str = Query(..., description="Project root path")):
    root = Path(path).resolve()
    project = _get_or_scan_project(root)

    if not project.graph:
        return GraphData(nodes=[], edges=[])

    nodes = []
    for n in project.graph.nodes:
        nodes.append({
            "id": n.id,
            "label": n.name,
            "type": n.type.value,
        })

    edges = []
    for e in project.graph.edges:
        edges.append({
            "source": e.source,
            "target": e.target,
            "label": e.relation.value,
        })

    return GraphData(nodes=nodes, edges=edges)


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    children: list[FileTreeNode] = []


@app.get("/project/files", response_model=list[FileTreeNode])
async def get_file_tree(path: str = Query(..., description="Project root path")):
    root = Path(path).resolve()
    project = _get_or_scan_project(root)

    tree: dict[str, Any] = {}
    for f in project.indexed_files:
        rel = f.path.relative_to(root)
        parts = rel.parts
        current = tree
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            if part not in current:
                current[part] = {
                    "name": part,
                    "path": str(rel),
                    "type": "file" if is_last else "directory",
                    "children": {} if not is_last else [],
                    "_symbols": [],
                }
                if is_last and f.analysis:
                    for sym in f.analysis.symbols[:20]:
                        current[part]["_symbols"].append({
                            "name": sym.name,
                            "kind": sym.kind,
                            "line": sym.line,
                        })
            current = current[part] if is_last else current[part]["children"]

    def _build(node: dict) -> dict:
        result = {
            "name": node["name"],
            "path": node["path"],
            "type": node["type"],
        }
        if node["type"] == "directory":
            result["children"] = [_build(n) for n in node["children"].values()]
        if node["_symbols"]:
            result["symbols"] = node["_symbols"]
        return result

    # Sort: directories first, then files
    sorted_children = sorted(tree.values(), key=lambda n: (0 if n["type"] == "directory" else 1, n["name"]))
    return [_build(n) for n in sorted_children]


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the EDITH Mission Control dashboard."""
    dash_path = STATIC_DIR / "dashboard.html"
    if dash_path.exists():
        return HTMLResponse(dash_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard not built yet</h1>")


@app.get("/review")
async def get_review(path: str = Query(..., description="Project root path")):
    """Run a full engineering review and return scores per dimension."""
    root = Path(path).resolve()
    if not root.exists():
        raise HTTPException(400, f"Path does not exist: {root}")

    project = _get_or_scan_project(root)
    engine = ReviewEngine()
    report = engine.review(project)

    d = report.to_dict()
    return {
        "overall": report.score.overall,
        "dimensions": [
            {"name": dim.name, "score": dim.score}
            for dim in report.score.dimensions
        ],
        "strengths": report.score.strengths,
        "weaknesses": report.score.weaknesses,
        "recommendations": report.recommendations,
        "metrics": d.get("metrics", {}),
    }


@app.get("/autonomous/opportunities")
async def get_opportunities(
    path: str = Query(..., description="Project root path"),
    max: int = Query(20, description="Max opportunities to return"),
):
    """Find improvement opportunities in a project."""
    root = Path(path).resolve()
    if not root.exists():
        raise HTTPException(400, f"Path does not exist: {root}")

    project = _get_or_scan_project(root)
    engine = AutonomousEngine(max_opportunities=max, use_llm=False)
    opportunities = engine.find_opportunities(project)

    return {
        "opportunities": [
            {
                "severity": opp.severity.value,
                "type": opp.type.value,
                "description": opp.description,
                "file_path": opp.file_path,
                "line": opp.line,
                "symbol_name": opp.symbol_name,
                "current_value": opp.current_value,
                "metric_name": opp.metric_name,
                "recommendation": opp.recommendation,
                "impact": opp.severity_score,
            }
            for opp in opportunities
        ],
        "total": len(opportunities),
    }


@app.get("/projects")
async def list_projects():
    """List all cached projects in the database."""
    try:
        _, db_memory = _get_db()
        cursor = db_memory.project_repo.get_cursor()
        cursor.execute(
            "SELECT id, name, path, last_scan FROM projects ORDER BY last_scan DESC"
        )
        rows = cursor.fetchall()
        return [
            {"id": r["id"], "name": r["name"], "path": r["path"], "last_scan": r["last_scan"]}
            for r in rows
        ]
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# LLM Provider Endpoints
# ---------------------------------------------------------------------------

class SetModelRequest(BaseModel):
    provider: str | None = None
    model: str


@app.get("/llm/status")
async def llm_status():
    """Return the current provider status, active model, and health.

    The dashboard uses this to display the model info panel.
    """
    provider = ProviderFactory.get_cached()
    if provider is None:
        # Try to create one
        import os
        if os.environ.get("EDITH_LLM__PROVIDER"):
            provider = ProviderFactory.create()

    if provider is None:
        return {
            "configured": False,
            "provider": None,
            "model": None,
            "healthy": None,
            "models": [],
            "info": None,
        }

    info = provider.model_info
    healthy = provider.health_check()
    models = provider.list_models()

    return {
        "configured": True,
        "provider": provider.provider_name,
        "model": provider.model_name,
        "healthy": healthy,
        "models": models,
        "info": info,
        "config": {
            "provider": llm_settings.provider,
            "ollama_model": llm_settings.ollama_model,
            "openai_model": llm_settings.openai_model,
        },
    }


@app.get("/llm/models")
async def llm_models():
    """List available models from the current provider."""
    provider = ProviderFactory.create()
    models = provider.list_models()
    return {
        "provider": provider.provider_name,
        "current": provider.model_name,
        "models": models,
    }


@app.post("/llm/set-model")
async def llm_set_model(req: SetModelRequest):
    """Hot-switch the active model without restarting.

    If ``provider`` is specified and differs from the current one,
    the factory creates a new provider instance. Otherwise just
    calls ``set_model()`` on the existing provider.
    """
    provider = ProviderFactory.create()

    if req.provider and req.provider != provider.provider_name:
        # Switch to a different provider entirely
        provider = ProviderFactory.rebuild(req.provider)

    provider.set_model(req.model)

    return {
        "status": "ok",
        "provider": provider.provider_name,
        "model": provider.model_name,
        "info": provider.model_info,
    }


@app.post("/llm/chat")
async def llm_chat(messages: list[dict]):
    """Send a chat message to the current LLM provider."""
    provider = ProviderFactory.create()
    answer = provider.chat(messages)
    return {"answer": answer}


@app.get("/llm/health")
async def llm_health():
    """Check if the current provider is reachable."""
    provider = ProviderFactory.create()
    healthy = provider.health_check()
    return {
        "healthy": healthy,
        "provider": provider.provider_name,
        "model": provider.model_name,
    }


# ---------------------------------------------------------------------------
# WebSocket — streaming chat
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    logger.debug("WebSocket connected")

    memory = ConversationMemory()
    engine = ContextEngine(memory=memory)
    builder = PromptBuilder()
    detector = IntentDetector()
    provider = _get_provider()
    current_project: Project | None = None

    try:
        while True:
            data = await ws.receive_text()

            # Special command: set project path
            if data.startswith("//project "):
                path_str = data[len("//project "):].strip()
                root = Path(path_str).resolve()
                if root.exists():
                    current_project = _get_or_scan_project(root)
                    await ws.send_text(json.dumps({
                        "type": "system",
                        "message": f"Loaded project: {root.name}",
                        "project": _project_to_summary(current_project),
                    }))
                else:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": f"Path does not exist: {path_str}",
                    }))
                continue

            # Special command: force re-scan
            if data.startswith("//rescan"):
                if current_project:
                    current_project = _get_or_scan_project(current_project.root, force=True)
                    await ws.send_text(json.dumps({
                        "type": "system",
                        "message": f"Re-scanned: {current_project.root.name}",
                        "project": _project_to_summary(current_project),
                    }))
                else:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "message": "No project loaded. Use //project <path> first.",
                    }))
                continue

            if current_project is None:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": "No project loaded. Use //project <path> first.",
                }))
                continue

            # Process the question
            question = data
            intent, target = detector.detect(question)
            context = engine.build_context(question, current_project, intent=intent, target=target)
            prompt = builder.build(question, context, current_project)

            # Send intent info
            await ws.send_text(json.dumps({
                "type": "intent",
                "intent": intent.value,
                "target": target,
            }))

            # Stream the answer
            full_answer = ""
            async for chunk in _async_stream(provider, prompt):
                full_answer += chunk
                await ws.send_text(json.dumps({
                    "type": "chunk",
                    "text": chunk,
                }))

            # Signal completion
            await ws.send_text(json.dumps({
                "type": "done",
                "answer": full_answer,
            }))

            memory.add_turn(question, full_answer, intent=intent.value, entities=[target] if target else [])

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


async def _async_stream(provider, prompt: str):
    """Wrap a synchronous stream generator into an async generator."""
    import asyncio
    loop = asyncio.get_event_loop()
    iterator = iter(provider.ask_stream(prompt))
    while True:
        try:
            chunk = await loop.run_in_executor(None, next, iterator)
            yield chunk
        except StopIteration:
            break


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api:app", host="127.0.0.1", port=8765, reload=True)
