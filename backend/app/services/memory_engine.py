from typing import Dict, Any
from app.core.config import logger
from app.models.project import Project


class MemoryEngine:
    """Simple Memory Engine stub.

    Responsibilities:
    - Persist extracted knowledge (in-memory or delegated store)
    - Provide query interface for later Context Engine use
    """

    def __init__(self):
        # In-memory store keyed by project id or name for now
        self._store: Dict[str, Any] = {}

    def save_project(self, project: Project) -> None:
        key = getattr(project, "name", "default")
        logger.debug("MemoryEngine: saving project %s", key)
        # Store a lightweight snapshot (avoid storing large binary blobs)
        self._store[key] = {
            "files": [f.path.as_posix() for f in project.indexed_files],
            "symbols_count": sum(len(f.analysis.symbols) if f.analysis else 0 for f in project.indexed_files),
        }

    def query(self, key: str) -> Any:
        logger.debug("MemoryEngine: query %s", key)
        return self._store.get(key)
