"""Coupling Graph Visualizer — generates an interactive D3.js force-directed
graph of module dependencies.

Output is a **standalone, self-contained HTML file** — no server needed.

Usage::

    from app.review.visualizer import CouplingGraphVisualizer

    viz = CouplingGraphVisualizer()
    html = viz.generate(nodes, edges)
    Path("coupling.html").write_text(html, encoding="utf-8")
"""

from __future__ import annotations

import html as html_mod
from pathlib import Path


# D3.js version pinned for reproducibility
D3_VERSION = "7"

# Colour palette — one colour per layer
LAYER_COLORS: dict[str, str] = {
    "core":      "#e74c3c",  # red
    "database":  "#e67e22",  # orange
    "models":    "#f1c40f",  # yellow
    "graph":     "#2ecc71",  # green
    "services":  "#1abc9c",  # teal
    "analyzers": "#3498db",  # blue
    "ai":        "#9b59b6",  # purple
    "review":    "#8e44ad",  # dark purple
    "api":       "#34495e",  # dark grey
    "static":    "#7f8c8d",  # medium grey
    "other":     "#95a5a6",  # light grey
}

# HTML template — the full D3.js force-directed graph
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDITH — File Coupling Graph: {PROJECT_NAME}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    overflow: hidden;
    height: 100vh;
  }}
  #header {{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 100;
    padding: 12px 24px;
    background: rgba(26,26,46,0.92);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  #header h1 {{
    font-size: 18px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }}
  #header h1 span {{
    color: #64ffda;
    font-weight: 300;
  }}
  #legend {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    opacity: 0.85;
  }}
  .legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }}
  #stats {{
    font-size: 12px;
    opacity: 0.6;
  }}
  svg {{
    width: 100%;
    height: 100vh;
    display: block;
  }}
  .links line {{
    stroke-opacity: 0.4;
    transition: stroke-opacity 0.2s;
  }}
  .links line:hover {{
    stroke-opacity: 0.8;
  }}
  .nodes circle {{
    stroke: rgba(255,255,255,0.15);
    stroke-width: 1.5;
    cursor: pointer;
    transition: r 0.15s, stroke-width 0.15s;
  }}
  .nodes circle:hover {{
    stroke: #64ffda;
    stroke-width: 2.5;
  }}
  .nodes text {{
    pointer-events: none;
    font-size: 10px;
    fill: rgba(255,255,255,0.75);
    text-shadow: 0 1px 3px rgba(0,0,0,0.6);
    opacity: 0;
    transition: opacity 0.2s;
  }}
  .nodes text.visible {{
    opacity: 1;
  }}
  #tooltip {{
    position: fixed;
    padding: 10px 14px;
    background: rgba(0,0,0,0.85);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(100,255,218,0.3);
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 200;
    max-width: 420px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }}
  #tooltip.visible {{
    opacity: 1;
  }}
  #tooltip .tooltip-title {{
    font-weight: 600;
    color: #64ffda;
    margin-bottom: 4px;
  }}
  #tooltip .tooltip-path {{
    font-size: 11px;
    opacity: 0.6;
    word-break: break-all;
  }}
  #tooltip .tooltip-stat {{
    font-size: 11px;
    margin-top: 4px;
    opacity: 0.8;
  }}
  .controls {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 100;
    display: flex;
    gap: 8px;
  }}
  .controls button {{
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    color: #e0e0e0;
    padding: 8px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.2s;
  }}
  .controls button:hover {{
    background: rgba(100,255,218,0.15);
    border-color: #64ffda;
  }}
  .search-box {{
    position: fixed;
    top: 70px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 100;
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 8px 16px;
    width: 320px;
    max-width: 90vw;
    color: #e0e0e0;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }}
  .search-box:focus {{
    border-color: #64ffda;
  }}
  .search-box::placeholder {{
    color: rgba(255,255,255,0.3);
  }}
</style>
</head>
<body>

<div id="header">
  <h1>EDITH <span>⟡</span> {PROJECT_NAME}</h1>
  <div id="legend">
    {LEGEND_ITEMS}
    <span id="stats"></span>
  </div>
</div>

<input class="search-box" id="search" type="text" placeholder="Search files…" autofocus>

<div id="tooltip"></div>

<div class="controls">
  <button onclick="zoomReset()">⟲ Reset</button>
  <button onclick="toggleLabels()">🏷 Labels</button>
</div>

<svg id="graph"></svg>

<script src="https://d3js.org/d3.v{D3_VERSION}.min.js"></script>
<script>
// ── Data ──────────────────────────────────────────────────────────
const NODES = {NODES_JSON};
const EDGES = {EDGES_JSON};

// ── Colour map ────────────────────────────────────────────────────
const COLOR_MAP = {COLOR_MAP_JSON};

// ── SVG setup ─────────────────────────────────────────────────────
const svg = d3.select("#graph");
const width = window.innerWidth;
const height = window.innerHeight;

svg.attr("viewBox", [0, 0, width, height]);

// ── Controls ──────────────────────────────────────────────────────
const gLinks = svg.append("g").attr("class", "links");
const gNodes = svg.append("g").attr("class", "nodes");
const tooltip = d3.select("#tooltip");
const statsEl = d3.select("#stats");
let labelsVisible = false;

// ── Scale radii ───────────────────────────────────────────────────
const weightExtent = d3.extent(EDGES, d => d.weight);
const radiusScale = d3.scaleSqrt()
  .domain(weightExtent)
  .range([3, 12]);

const edgeWidthScale = d3.scaleSqrt()
  .domain(weightExtent)
  .range([0.5, 4]);

// ── Force simulation ──────────────────────────────────────────────
const simulation = d3.forceSimulation(NODES)
  .force("link", d3.forceLink(EDGES)
    .id(d => d.id)
    .distance(d => 200 - d.weight * 8)
    .strength(d => 0.3 + d.weight * 0.05))
  .force("charge", d3.forceManyBody().strength(-250))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collision", d3.forceCollide(d => radiusScale(d.weight || 1) + 10));

// ── Links ─────────────────────────────────────────────────────────
const link = gLinks.selectAll("line")
  .data(EDGES)
  .join("line")
  .attr("stroke", d => COLOR_MAP[NODES.find(n => n.id === d.target)?.layer || "other"])
  .attr("stroke-width", d => edgeWidthScale(d.weight))
  .attr("stroke-dasharray", d => d.is_cycle ? "4,3" : null)
  .on("mouseenter", function(event, d) {{
    showTooltip(event, `
      <div class="tooltip-title">⟶ Import</div>
      <div class="tooltip-path">${{getShortPath(d.source.id)}}</div>
      <div class="tooltip-path" style="opacity:0.4;">↓</div>
      <div class="tooltip-path">${{getShortPath(d.target.id)}}</div>
      <div class="tooltip-stat">${{d.label}}</div>
    `);
  }})
  .on("mousemove", moveTooltip)
  .on("mouseleave", hideTooltip);

// ── Nodes ─────────────────────────────────────────────────────────
const node = gNodes.selectAll("g")
  .data(NODES)
  .join("g")
  .call(d3.drag()
    .on("start", dragStarted)
    .on("drag", dragged)
    .on("end", dragEnded));

node.append("circle")
  .attr("r", d => Math.max(4, radiusScale(d.weight || 1)))
  .attr("fill", d => COLOR_MAP[d.layer] || "#95a5a6")
  .attr("opacity", 0.9)
  .on("mouseenter", function(event, d) {{
    const deps = EDGES.filter(e => e.source.id === d.id || e.target.id === d.id);
    const inCount = deps.filter(e => e.target.id === d.id).length;
    const outCount = deps.filter(e => e.source.id === d.id).length;
    showTooltip(event, `
      <div class="tooltip-title">${{d.name}}</div>
      <div class="tooltip-path">${{d.path}}</div>
      <div class="tooltip-stat">Layer: ${{d.layer}}</div>
      <div class="tooltip-stat">← ${{inCount}} incoming  |  → ${{outCount}} outgoing</div>
    `);
  }})
  .on("mousemove", moveTooltip)
  .on("mouseleave", hideTooltip);

node.append("text")
  .text(d => d.name)
  .attr("dx", d => Math.max(4, radiusScale(d.weight || 1)) + 6)
  .attr("dy", 4);

// ── Tick ──────────────────────────────────────────────────────────
simulation.on("tick", () => {{
  link
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);

  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});

// ── Zoom ──────────────────────────────────────────────────────────
const zoom = d3.zoom()
  .scaleExtent([0.1, 4])
  .on("zoom", (event) => {{
    gLinks.attr("transform", event.transform);
    gNodes.attr("transform", event.transform);
  }});

svg.call(zoom);

function zoomReset() {{
  svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
}}

// ── Labels toggle ─────────────────────────────────────────────────
function toggleLabels() {{
  labelsVisible = !labelsVisible;
  node.selectAll("text").classed("visible", labelsVisible);
}}

// ── Search ────────────────────────────────────────────────────────
document.getElementById("search").addEventListener("input", function() {{
  const q = this.value.toLowerCase();
  node.each(function(d) {{
    const match = q === "" || d.name.toLowerCase().includes(q) || d.path.toLowerCase().includes(q);
    d3.select(this).style("opacity", match ? 1 : 0.15);
  }});
  link.style("opacity", function(d) {{
    const src = d.source.id || d.source;
    const tgt = d.target.id || d.target;
    return q === ""
      ? 1
      : src.toLowerCase().includes(q) || tgt.toLowerCase().includes(q)
        ? 0.8
        : 0.05;
  }});
}});

// ── Tooltip helpers ───────────────────────────────────────────────
function showTooltip(event, html) {{
  tooltip.html(html).classed("visible", true);
  moveTooltip(event);
}}

function moveTooltip(event) {{
  tooltip
    .style("left", (event.clientX + 16) + "px")
    .style("top", (event.clientY - 10) + "px");
}}

function hideTooltip() {{
  tooltip.classed("visible", false);
}}

function getShortPath(path) {{
  const parts = path.replace(/\\\\/g, "/").split("/");
  return parts.length > 4 ? ".../" + parts.slice(-3).join("/") : path;
}}

// ── Drag helpers ──────────────────────────────────────────────────
function dragStarted(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}}

function dragged(event, d) {{
  d.fx = event.x;
  d.fy = event.y;
}}

function dragEnded(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}}

// ── Stats ─────────────────────────────────────────────────────────
statsEl.text(`${{NODES.length}} files · ${{EDGES.length}} dependencies`);

// ── Resize ─────────────────────────────────────────────────────────
window.addEventListener("resize", () => {{
  const w = window.innerWidth;
  const h = window.innerHeight;
  svg.attr("viewBox", [0, 0, w, h]);
  simulation.force("center", d3.forceCenter(w / 2, h / 2));
  simulation.alpha(0.3).restart();
}});
</script>
</body>
</html>
"""


class CouplingGraphVisualizer:
    """Generates a standalone HTML file with a D3.js coupling graph."""

    def generate(
        self,
        project_name: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> str:
        """Generate the full HTML page.

        Args:
            project_name: Name of the project (for the title).
            nodes: List of node dicts (``id``, ``name``, ``path``, ``layer``, ``group``).
            edges: List of edge dicts (``source``, ``target``, ``weight``).

        Returns:
            A complete standalone HTML string.
        """
        # Assign node weights (total degree) for sizing
        deg: dict[str, int] = {}
        for e in edges:
            s = e["source"] if isinstance(e["source"], str) else e["source"]["id"]
            t = e["target"] if isinstance(e["target"], str) else e["target"]["id"]
            deg[s] = deg.get(s, 0) + e.get("weight", 1)
            deg[t] = deg.get(t, 0) + e.get("weight", 1)

        for n in nodes:
            n["weight"] = deg.get(n["id"], 1)

        # Sort nodes so larger ones render first (behind)
        nodes_sorted = sorted(nodes, key=lambda n: n.get("weight", 1), reverse=True)

        import json

        nodes_json = json.dumps(nodes_sorted, indent=0)
        edges_json = json.dumps(edges, indent=0)
        color_map_json = json.dumps(LAYER_COLORS, indent=0)

        # Build legend
        legend_rows: list[str] = []
        for layer, color in LAYER_COLORS.items():
            legend_rows.append(
                f'<span class="legend-item">'
                f'<span class="legend-dot" style="background:{color}"></span>'
                f"{layer}</span>"
            )
        legend_html = " ".join(legend_rows)

        html = (
            HTML_TEMPLATE
            .replace("{PROJECT_NAME}", html_mod.escape(project_name))
            .replace("{D3_VERSION}", D3_VERSION)
            .replace("{NODES_JSON}", nodes_json)
            .replace("{EDGES_JSON}", edges_json)
            .replace("{COLOR_MAP_JSON}", color_map_json)
            .replace("{LEGEND_ITEMS}", legend_html)
        )

        return html

    def save(
        self,
        project_name: str,
        nodes: list[dict],
        edges: list[dict],
        output_path: str | Path = "coupling_graph.html",
    ) -> Path:
        """Generate and save the graph to a file.

        Returns the path to the saved file.
        """
        html = self.generate(project_name, nodes, edges)
        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return path.absolute()
