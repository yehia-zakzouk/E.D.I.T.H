"""Architecture Analyzer — evaluates project structure.

Factors
-------
1. **Coupling** — how many dependencies exist between files
2. **Cohesion** — how focused each module is (responsibility count)
3. **Layer violations** — imports that cross architectural boundaries
4. **Cyclic dependencies** — A imports B imports A
5. **Module size distribution** — are modules reasonably sized?
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.models.project import Project
from app.models.file_analysis import FileAnalysis
from app.models.relationship import Relationship


class ArchitectureAnalyzer:
    """Evaluates the architecture of a repository."""

    # Layers (Python-specific, ordered from low-level to high-level)
    LAYERS = [
        "core",
        "database",
        "models",
        "graph",
        "services",
        "analyzers",
        "ai",
        "review",
        "api",
        "static",
    ]

    def analyze_project(self, project: Project) -> dict:
        """Run architecture analysis on the entire project.

        Returns a dict of architecture metrics.
        """
        total_files = len(project.indexed_files)
        if total_files == 0:
            return {
                "afferent_coupling": 0,
                "efferent_coupling": 0,
                "instability": 0.0,
                "abstractness": 0.0,
                "layer_violations": 0,
                "cyclic_dependencies": 0,
                "module_scores": {},
            }

        import_graph, reverse_imports = self._build_import_graph(project)

        # --- Afferent / Efferent coupling ---
        # Afferent (Ca): how many other modules depend on this one
        # Efferent (Ce): how many modules this one depends on
        afferent_coupling: dict[str, int] = {}
        efferent_coupling: dict[str, int] = {}

        for path in import_graph:
            efferent_coupling[path] = len(import_graph[path])
        for path in reverse_imports:
            afferent_coupling[path] = len(reverse_imports[path])

        avg_afferent = sum(afferent_coupling.values()) / max(len(afferent_coupling), 1)
        avg_efferent = sum(efferent_coupling.values()) / max(len(efferent_coupling), 1)

        # --- Instability (Martin's metric) ---
        # I = Ce / (Ca + Ce) — 0 is stable, 1 is unstable
        instabilities: list[float] = []
        for path in import_graph:
            ca = afferent_coupling.get(path, 0)
            ce = efferent_coupling.get(path, 0)
            if ca + ce > 0:
                instabilities.append(ce / (ca + ce))
        avg_instability = sum(instabilities) / max(len(instabilities), 1) if instabilities else 0.0

        # --- Layer violations ---
        layer_violations = self._count_layer_violations(import_graph, project)

        # --- Cyclic dependencies ---
        cycles = self._find_cycles(import_graph)

        # --- Module scores (per-directory) ---
        module_scores = self._score_modules(project)

        return {
            "total_files": total_files,
            "afferent_coupling": round(avg_afferent, 2),
            "efferent_coupling": round(avg_efferent, 2),
            "instability": round(avg_instability, 3),
            "layer_violations": layer_violations,
            "cyclic_dependencies": len(cycles),
            "cycle_list": [list(c) for c in cycles[:5]],
            "module_scores": module_scores,
        }

    def get_coupling_graph(self, project: Project) -> tuple[list[dict], list[dict]]:
        """Build a force-directed-graph-friendly coupling graph.

        Returns
        -------
        (nodes, edges)
            nodes: list of dicts with keys ``id``, ``name``, ``layer``, ``group``
            edges: list of dicts with keys ``source``, ``target``, ``weight``,
                   ``is_cycle``, ``label``
        """
        import_graph, _ = self._build_import_graph(project)

        # Detect cycles in the import graph
        cycle_edges: set[tuple[str, str]] = set()
        for a in import_graph:
            for b in import_graph[a]:
                if b in import_graph and a in import_graph[b]:
                    cycle_edges.add((a, b))
                    cycle_edges.add((b, a))

        node_set: dict[str, dict] = {}
        edge_map: dict[tuple[str, str], int] = defaultdict(int)

        for source_path, targets in import_graph.items():
            if source_path not in node_set:
                node_set[source_path] = self._make_node(source_path)
            for resolved in targets:
                if resolved not in node_set:
                    node_set[resolved] = self._make_node(resolved)
                edge_map[(source_path, resolved)] += 1

        nodes = list(node_set.values())
        edges = [
            {
                "source": src,
                "target": tgt,
                "weight": min(w, 20),
                "is_cycle": (src, tgt) in cycle_edges,
                "label": f"{w} import{'s' if w > 1 else ''}",
            }
            for (src, tgt), w in edge_map.items()
        ]

        return nodes, edges

    def _make_node(self, path: str) -> dict:
        """Create a node dict for a file path."""
        p = Path(path)
        layer = self._detect_layer(path) or "other"
        return {
            "id": path,
            "name": p.name,
            "path": path,
            "layer": layer,
            "group": self.LAYERS.index(layer) + 1 if layer in self.LAYERS else 99,
        }

    # ------------------------------------------------------------------
    # Internal — shared helpers
    # ------------------------------------------------------------------

    def _build_import_graph(
        self,
        project: Project,
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Build the forward and reverse import graphs from indexed files.

        Returns
        -------
        (import_graph, reverse_imports)
            import_graph: file_path → set of files it imports
            reverse_imports: file_path → set of files that import it
        """
        import_graph: dict[str, set[str]] = defaultdict(set)
        reverse_imports: dict[str, set[str]] = defaultdict(set)

        for fi in project.indexed_files:
            if fi.analysis is None:
                continue
            source_path = str(fi.path)
            for imp in fi.analysis.imports:
                resolved = self._resolve_import(imp, project)
                if resolved:
                    import_graph[source_path].add(resolved)
                    reverse_imports[resolved].add(source_path)

        return import_graph, reverse_imports

    def _resolve_import(self, import_name: str, project: Project) -> Optional[str]:
        """Try to resolve an import string to a file path in the project.

        .. caution::

            This uses a simple substring match (``import_path in path_str``),
            which can produce false positives (e.g. ``app.core`` matching
            ``app/core/decorators.py``). A proper resolver would use
            Python's ``importlib`` or ``sys.path`` resolution.

            This is sufficient for a heuristic first pass. The layer-violation
            count should be treated as directional, not exact.
        """
        import_path = import_name.replace(".", "/")

        for fi in project.indexed_files:
            path_str = str(fi.path)
            # Match the import to a file (e.g., "app.core.config" -> "app/core/config.py")
            if import_path in path_str.replace("\\", "/").replace(".py", ""):
                return path_str

        return None

    def _count_layer_violations(
        self,
        import_graph: dict[str, set[str]],
        project: Project,
    ) -> int:
        """Count imports that go from a higher layer to a lower layer."""
        violations = 0

        for source in import_graph:
            source_layer = self._detect_layer(source)
            for target in import_graph[source]:
                target_layer = self._detect_layer(target)

                if source_layer is not None and target_layer is not None:
                    # Lower index = lower level. Violation if low-level imports high-level
                    source_idx = self.LAYERS.index(source_layer)
                    target_idx = self.LAYERS.index(target_layer)

                    if target_idx < source_idx:
                        # Low-level layer depends on higher-level layer
                        violations += 1

        return violations

    def _detect_layer(self, path: str) -> Optional[str]:
        """Detect which architectural layer a file belongs to."""
        path_lower = path.replace("\\", "/").lower()
        for layer in self.LAYERS:
            if f"/{layer}/" in path_lower or path_lower.endswith(f"/{layer}"):
                return layer
        return None

    def _find_cycles(self, import_graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
        """Find simple 2-node and 3-node cycles in the import graph."""
        cycles: set[tuple[str, ...]] = set()

        paths = list(import_graph.keys())
        for i, a in enumerate(paths):
            for b in import_graph.get(a, set()):
                if b in import_graph and a in import_graph[b]:
                    cycle = tuple(sorted([a, b]))
                    cycles.add(cycle)
                # 3-node cycles
                for c in import_graph.get(b, set()):
                    if c in import_graph and a in import_graph[c]:
                        cycle = tuple(sorted([a, b, c]))
                        cycles.add(cycle)

        return [c for c in cycles if c]

    def _score_modules(self, project: Project) -> dict[str, float]:
        """Score each module directory on size and responsibility focus."""
        dir_sizes: dict[str, int] = defaultdict(int)
        dir_files: dict[str, int] = defaultdict(int)

        for fi in project.indexed_files:
            parent = str(fi.path.parent)
            dir_sizes[parent] += fi.lines if hasattr(fi, "lines") else 0
            dir_files[parent] += 1

        scores = {}
        for directory, size in dir_sizes.items():
            # Very large modules or very small modules get lower scores
            file_count = dir_files[directory]
            if file_count == 0:
                scores[directory] = 0.5
                continue

            avg_size = size / file_count
            if 50 <= avg_size <= 300:
                size_score = 1.0
            elif avg_size < 50:
                size_score = avg_size / 50
            else:
                size_score = max(0, 1 - (avg_size - 300) / 700)

            scores[directory] = round(size_score, 2)

        return scores
